from flask import jsonify, request
from pydantic import ValidationError

from app.api import api_bp
from app.auth.decorators import admin_required, aprovado_required
from app.extensions import db, limiter
from app.models import Cidade, PerfilCidade, ModoPrazo, TipoAberturaFDS
from app.schemas import CidadeIn

# ATENÇÃO DE SEGURANÇA: nenhuma rota autenticada deste arquivo usa
# @cache.cached(). Cachear a *resposta HTTP inteira* de uma rota que passa
# por login_required/current_user é perigoso: o Flask reemite o cookie de
# sessão (Set-Cookie) a cada requisição autenticada, e o Flask-Caching
# armazenaria esse header junto com o corpo — servindo o cookie de sessão
# de UM usuário para QUALQUER outro que caia no mesmo cache (inclusive em
# outro navegador). Foi exatamente isso que causava sessões "vazando"
# entre navegadores. Se precisar de cache aqui no futuro, cacheie apenas o
# dado (ex.: `cache.memoize()` numa função auxiliar que não seja a view
# Flask), nunca a rota autenticada inteira.


def _cidade_from_payload(data: CidadeIn) -> dict:
    """Converte o schema Pydantic (camelCase, igual ao front) para os campos
    (snake_case + Enum) usados pelo modelo SQLAlchemy."""
    campos = {
        "nome": data.nome,
        "perfil": PerfilCidade(data.perfil),
        "modo_prazo": ModoPrazo(data.modoPrazo),
        "prazo_inicio": data.prazoInicio if data.modoPrazo != "semData" else None,
        "prazo_fim": data.prazoFim if data.modoPrazo != "semData" else None,
        "regra_horas": data.regraHoras,
        "observacao": data.observacao,
        "tecnicos_fim_semana": data.tecnicosFimSemana,
        "tipo_abertura_fim_semana": TipoAberturaFDS(data.tipoAberturaFimSemana),
        "plantonista_fds": data.plantonistaFDS,
        "modo_auto_plantonista": data.modoAutoPlantonista,
    }
    if data.imagemUrl is not None:
        campos["imagem_url"] = data.imagemUrl or None
    return campos


@api_bp.get("/cidades")
@aprovado_required
# Recarregada sempre que /api/sync detecta mudança nas cidades — limite
# próprio pelo mesmo motivo de /api/sync e /api/avisos (ver app/api/sync.py).
@limiter.limit("60 per minute")
def listar_cidades():
    q = (request.args.get("q") or "").strip().lower()
    query = Cidade.query.order_by(Cidade.nome.asc())
    cidades = query.all()
    if q:
        cidades = [
            c
            for c in cidades
            if q in c.nome.lower()
            or q in c.perfil.value.lower()
            or (c.regra_horas and q in c.regra_horas.lower())
        ]
    return jsonify([c.to_dict() for c in cidades])


@api_bp.get("/cidades/<int:cidade_id>")
@aprovado_required
def obter_cidade(cidade_id):
    cidade = Cidade.query.get_or_404(cidade_id)
    return jsonify(cidade.to_dict())


@api_bp.post("/cidades")
@admin_required
@limiter.limit("60 per minute")
def criar_cidade():
    payload = request.get_json(silent=True) or {}
    try:
        data = CidadeIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    cidade = Cidade(**_cidade_from_payload(data))
    db.session.add(cidade)
    db.session.commit()
    return jsonify(cidade.to_dict()), 201


@api_bp.put("/cidades/<int:cidade_id>")
@admin_required
@limiter.limit("60 per minute")
def atualizar_cidade(cidade_id):
    cidade = Cidade.query.get_or_404(cidade_id)
    payload = request.get_json(silent=True) or {}
    try:
        data = CidadeIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    for campo, valor in _cidade_from_payload(data).items():
        setattr(cidade, campo, valor)
    db.session.commit()
    return jsonify(cidade.to_dict())


@api_bp.delete("/cidades/<int:cidade_id>")
@admin_required
@limiter.limit("30 per minute")
def excluir_cidade(cidade_id):
    cidade = Cidade.query.get_or_404(cidade_id)
    nome = cidade.nome
    # Ver o comentário equivalente em app/api/avisos.py: delete por
    # condição (Core) devolve a contagem real de linhas afetadas, o que é
    # confiável sob concorrência — ao contrário de session.delete(obj) +
    # commit(), cujo aviso de "já não existe mais" (StaleDataError) o
    # driver do SQLite não reporta de forma confiável.
    linhas_apagadas = Cidade.query.filter_by(id=cidade_id).delete(synchronize_session=False)
    db.session.commit()
    if linhas_apagadas == 0:
        return jsonify({"error": "Esta cidade já havia sido excluída."}), 404
    return jsonify({"message": f'Cidade "{nome}" excluída com sucesso.'})


@api_bp.get("/cidades/estatisticas")
@admin_required
def estatisticas_cidades():
    matrizes = Cidade.query.filter_by(perfil=PerfilCidade.matriz).count()
    filiais = Cidade.query.filter_by(perfil=PerfilCidade.filial).count()
    return jsonify({"matrizes": matrizes, "filiais": filiais})
