from datetime import datetime

from flask import jsonify, request
from flask_login import current_user
from pydantic import ValidationError

from app.api import api_bp
from app.auth.decorators import admin_required, aprovado_required
from app.extensions import db, limiter
from app.models import Aviso, ModoDuracaoAviso, StatusAviso, TipoAviso
from app.schemas import AvisoIn

# ATENÇÃO DE SEGURANÇA: nenhuma rota autenticada deste arquivo usa
# @cache.cached() — ver o comentário equivalente em app/api/cidades.py.
# Cachear a resposta inteira de uma rota autenticada vazaria o cookie de
# sessão (Set-Cookie) de um usuário para outro.


def _aviso_from_payload(data: AvisoIn, aviso_existente: Aviso | None = None) -> dict:
    if data.modoDuracao == "horas":
        # Modo "duração em horas": a pessoa só informa quantas horas o
        # aviso deve durar — não precisa escolher uma data/hora de início.
        # A contagem começa agora (hora do servidor) quando o aviso é
        # criado, ou quando ele MUDA para o modo horas. Se já estava em
        # modo horas e a pessoa só ajustou o título/descrição/duração,
        # preservamos o início original — editar não deveria reiniciar a
        # contagem de algo que já estava em andamento por engano.
        if aviso_existente is not None and aviso_existente.modo_duracao == ModoDuracaoAviso.horas:
            inicio = aviso_existente.inicio
        else:
            inicio = datetime.now().strftime("%Y-%m-%dT%H:%M")
    else:
        inicio = data.inicio

    return {
        "titulo": data.titulo,
        "descricao": data.descricao,
        "tipo": TipoAviso(data.tipo),
        "imagem_url": data.imagemUrl or None,
        "modo_duracao": ModoDuracaoAviso(data.modoDuracao),
        "inicio": inicio,
        "fim": data.fim if data.modoDuracao == "dias" else None,
        "duracao_horas": data.duracaoHoras if data.modoDuracao == "horas" else None,
    }


def _pode_gerenciar(aviso: Aviso) -> bool:
    """Admin gerencia qualquer aviso; um usuário comum só o próprio."""
    return current_user.is_admin or aviso.autor_id == current_user.id


@api_bp.post("/avisos/upload-imagem")
@aprovado_required
@limiter.limit("20 per minute")
def upload_imagem_aviso():
    """Upload de imagem para ilustrar um aviso/informativo — qualquer
    usuário aprovado pode enviar (mesma regra de quem pode criar avisos).
    A imagem é automaticamente redimensionada/otimizada (ver
    processar_e_salvar_imagem em app/api/uploads.py), então não é preciso
    se preocupar com o tamanho do arquivo original."""
    from app.api.uploads import processar_e_salvar_imagem

    if "arquivo" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado (campo 'arquivo')."}), 400

    try:
        url_publica = processar_e_salvar_imagem(request.files["arquivo"], max_dim=1200)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    return jsonify({"url": url_publica}), 201


@api_bp.get("/avisos")
@aprovado_required
def listar_avisos():
    avisos = Aviso.query.order_by(Aviso.inicio.desc()).all()
    return jsonify([a.to_dict() for a in avisos])


@api_bp.get("/avisos/<int:aviso_id>")
@aprovado_required
def obter_aviso(aviso_id):
    aviso = Aviso.query.get_or_404(aviso_id)
    return jsonify(aviso.to_dict())


@api_bp.post("/avisos")
@aprovado_required
@limiter.limit("60 per minute")
def criar_aviso():
    """Qualquer usuário aprovado pode publicar um informativo — não só o
    admin. Cada um só pode depois editar/excluir os que ele mesmo criou;
    o admin pode gerenciar todos (ver _pode_gerenciar)."""
    payload = request.get_json(silent=True) or {}
    try:
        data = AvisoIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    aviso = Aviso(autor_id=current_user.id, **_aviso_from_payload(data))
    db.session.add(aviso)
    db.session.commit()
    return jsonify(aviso.to_dict()), 201


@api_bp.put("/avisos/<int:aviso_id>")
@aprovado_required
@limiter.limit("60 per minute")
def atualizar_aviso(aviso_id):
    aviso = Aviso.query.get_or_404(aviso_id)
    if not _pode_gerenciar(aviso):
        return jsonify({"error": "Você só pode editar os avisos que você mesmo criou."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        data = AvisoIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    for campo, valor in _aviso_from_payload(data, aviso_existente=aviso).items():
        setattr(aviso, campo, valor)
    db.session.commit()
    return jsonify(aviso.to_dict())


@api_bp.delete("/avisos/<int:aviso_id>")
@aprovado_required
@limiter.limit("30 per minute")
def excluir_aviso(aviso_id):
    aviso = Aviso.query.get_or_404(aviso_id)
    if not _pode_gerenciar(aviso):
        return jsonify({"error": "Você só pode excluir os avisos que você mesmo criou."}), 403

    titulo = aviso.titulo
    # Deleta por uma condição (Core), não por objeto (ORM) — o retorno é a
    # contagem REAL de linhas afetadas no banco. Isso importa sob
    # concorrência: se duas requisições tentarem excluir o mesmo aviso ao
    # mesmo tempo, a ORM (session.delete + commit) confia num aviso de
    # "linha já não existe mais" (StaleDataError) que o driver do SQLite
    # não reporta de forma confiável — a segunda requisição terminaria
    # retornando sucesso mesmo sem ter apagado nada. Conferir a contagem
    # aqui é a forma que funciona igual em SQLite e Postgres.
    linhas_apagadas = Aviso.query.filter_by(id=aviso_id).delete(synchronize_session=False)
    db.session.commit()
    if linhas_apagadas == 0:
        return jsonify({"error": "Este aviso já havia sido excluído."}), 404
    return jsonify({"message": f'Aviso "{titulo}" excluído com sucesso.'})


@api_bp.get("/avisos/estatisticas")
@admin_required
def estatisticas_avisos():
    avisos = Aviso.query.all()
    contagem = {StatusAviso.ativo.value: 0, StatusAviso.aguardando.value: 0, StatusAviso.expirado.value: 0}
    for a in avisos:
        contagem[a.calcular_status()] += 1
    return jsonify(contagem)
