from flask import jsonify, request
from flask_login import current_user
from pydantic import ValidationError
from sqlalchemy import and_, or_

from app.api import api_bp
from app.auth.decorators import aprovado_required
from app.extensions import db, limiter
from app.models import ChatMessage, User, GrupoChat, GrupoChatMembro, utcnow
from app.schemas import ChatMensagemIn, GrupoChatIn

MAX_MENSAGENS = 200


def _sou_membro(grupo_id: int) -> bool:
    return (
        GrupoChatMembro.query.filter_by(grupo_id=grupo_id, user_id=current_user.id).first()
        is not None
    )


def _sou_admin_do_grupo(grupo_id: int) -> bool:
    if current_user.is_admin:
        return True
    m = GrupoChatMembro.query.filter_by(grupo_id=grupo_id, user_id=current_user.id).first()
    return bool(m and m.papel == "admin")


@api_bp.get("/chat/usuarios")
@aprovado_required
def listar_usuarios_chat():
    """Diretório leve de pessoas para iniciar uma conversa privada — só o
    essencial para montar a lista (não é a rota de administração de
    usuários, que exige admin e traz status/aprovação)."""
    usuarios = (
        User.query.filter(User.status == "aprovado", User.id != current_user.id)
        .order_by(User.username)
        .all()
    )
    return jsonify([
        {
            "id": u.id,
            "username": u.username,
            "nome": u.nome or u.username,
            "fotoUrl": u.foto_url,
            "role": u.role.value,
        }
        for u in usuarios
    ])


# ------------------------------------------------------------------
# GRUPOS DE CHAT
# ------------------------------------------------------------------
@api_bp.get("/chat/grupos")
@aprovado_required
def listar_grupos():
    """Lista os grupos dos quais a pessoa logada participa (admin do
    sistema também vê todos os grupos, para fins de organização geral)."""
    if current_user.is_admin:
        grupos = GrupoChat.query.order_by(GrupoChat.nome).all()
    else:
        grupos = (
            GrupoChat.query.join(GrupoChatMembro)
            .filter(GrupoChatMembro.user_id == current_user.id)
            .order_by(GrupoChat.nome)
            .all()
        )
    return jsonify([g.to_dict(current_user_id=current_user.id) for g in grupos])


@api_bp.post("/chat/grupos")
@aprovado_required
@limiter.limit("20 per minute")
def criar_grupo():
    """Qualquer usuário aprovado pode criar um grupo — vira automaticamente
    o admin desse grupo (pode editar, adicionar/remover membros, excluir)."""
    payload = request.get_json(silent=True) or {}
    try:
        data = GrupoChatIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    grupo = GrupoChat(
        nome=data.nome, descricao=data.descricao, icone=data.icone, cor=data.cor,
        criado_por_id=current_user.id,
    )
    db.session.add(grupo)
    db.session.flush()  # garante grupo.id antes de criar os membros

    db.session.add(GrupoChatMembro(grupo_id=grupo.id, user_id=current_user.id, papel="admin"))
    membros_validos = User.query.filter(
        User.id.in_(data.membrosIds), User.status == "aprovado", User.id != current_user.id
    ).all()
    for u in membros_validos:
        db.session.add(GrupoChatMembro(grupo_id=grupo.id, user_id=u.id, papel="membro"))

    db.session.commit()
    return jsonify(grupo.to_dict(current_user_id=current_user.id)), 201


@api_bp.put("/chat/grupos/<int:grupo_id>")
@aprovado_required
@limiter.limit("20 per minute")
def editar_grupo(grupo_id):
    grupo = GrupoChat.query.get_or_404(grupo_id)
    if not _sou_admin_do_grupo(grupo_id):
        return jsonify({"error": "Só quem administra este grupo pode editá-lo."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        data = GrupoChatIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    grupo.nome = data.nome
    grupo.descricao = data.descricao
    grupo.icone = data.icone
    grupo.cor = data.cor
    db.session.commit()
    return jsonify(grupo.to_dict(current_user_id=current_user.id))


@api_bp.delete("/chat/grupos/<int:grupo_id>")
@aprovado_required
@limiter.limit("20 per minute")
def excluir_grupo(grupo_id):
    grupo = GrupoChat.query.get_or_404(grupo_id)
    if not _sou_admin_do_grupo(grupo_id):
        return jsonify({"error": "Só quem administra este grupo pode excluí-lo."}), 403

    nome = grupo.nome
    ChatMessage.query.filter_by(grupo_id=grupo_id).delete(synchronize_session=False)
    GrupoChatMembro.query.filter_by(grupo_id=grupo_id).delete(synchronize_session=False)
    linhas_apagadas = GrupoChat.query.filter_by(id=grupo_id).delete(synchronize_session=False)
    db.session.commit()
    if linhas_apagadas == 0:
        return jsonify({"error": "Este grupo já havia sido excluído."}), 404
    return jsonify({"message": f'Grupo "{nome}" excluído com sucesso.'})


@api_bp.get("/chat/grupos/<int:grupo_id>/membros")
@aprovado_required
def listar_membros_grupo(grupo_id):
    GrupoChat.query.get_or_404(grupo_id)
    if not _sou_membro(grupo_id) and not current_user.is_admin:
        return jsonify({"error": "Você não participa deste grupo."}), 403

    membros = (
        GrupoChatMembro.query.filter_by(grupo_id=grupo_id)
        .join(User)
        .order_by(User.username)
        .all()
    )
    return jsonify([
        {
            "id": m.usuario.id,
            "nome": m.usuario.nome or m.usuario.username,
            "fotoUrl": m.usuario.foto_url,
            "papel": m.papel,
        }
        for m in membros
    ])


@api_bp.post("/chat/grupos/<int:grupo_id>/membros")
@aprovado_required
@limiter.limit("30 per minute")
def adicionar_membros_grupo(grupo_id):
    GrupoChat.query.get_or_404(grupo_id)
    if not _sou_admin_do_grupo(grupo_id):
        return jsonify({"error": "Só quem administra este grupo pode adicionar membros."}), 403

    payload = request.get_json(silent=True) or {}
    ids = payload.get("membrosIds") or []
    if not isinstance(ids, list):
        return jsonify({"error": "Lista de membros inválida."}), 400

    ja_membros = {
        m.user_id for m in GrupoChatMembro.query.filter_by(grupo_id=grupo_id).all()
    }
    novos = User.query.filter(
        User.id.in_(ids), User.status == "aprovado", ~User.id.in_(ja_membros)
    ).all()
    for u in novos:
        db.session.add(GrupoChatMembro(grupo_id=grupo_id, user_id=u.id, papel="membro"))
    db.session.commit()
    return jsonify({"message": f"{len(novos)} membro(s) adicionado(s)."})


@api_bp.delete("/chat/grupos/<int:grupo_id>/membros/<int:user_id>")
@aprovado_required
@limiter.limit("30 per minute")
def remover_membro_grupo(grupo_id, user_id):
    GrupoChat.query.get_or_404(grupo_id)
    # Sair do próprio grupo é sempre permitido; remover outra pessoa exige
    # ser admin do grupo (ou admin do sistema).
    if user_id != current_user.id and not _sou_admin_do_grupo(grupo_id):
        return jsonify({"error": "Só quem administra este grupo pode remover outros membros."}), 403

    linhas_apagadas = GrupoChatMembro.query.filter_by(
        grupo_id=grupo_id, user_id=user_id
    ).delete(synchronize_session=False)
    db.session.commit()
    if linhas_apagadas == 0:
        return jsonify({"error": "Esta pessoa já não fazia parte do grupo."}), 404
    return jsonify({"message": "Membro removido do grupo."})


# ------------------------------------------------------------------
# MENSAGENS (chat geral / privado / grupo)
# ------------------------------------------------------------------
@api_bp.get("/chat/mensagens")
@aprovado_required
# Rota de polling (a cada 4s enquanto o chat está aberto, ~900 req/hora só
# de um usuário) — precisa de limite próprio, senão herda o default_limits
# global de 200/hora e passa a devolver 429 (silenciosamente ignorado pelo
# front-end) depois de poucos minutos de uso, fazendo o chat "travar" sem
# atualizar mensagens novas.
@limiter.limit("90 per minute")
def listar_mensagens():
    """Retorna as últimas mensagens (mais antigas primeiro), pronto para
    ser exibido direto na tela — o front faz polling simples nesta rota.

    - Sem parâmetros: chat geral (visível a todos aprovados).
    - `?com=<id>`: conversa privada entre a pessoa logada e esse usuário —
      nunca mensagens privadas de outras duplas, mesmo para o admin.
    - `?grupo=<id>`: mensagens desse grupo — exige ser membro dele.
    """
    destinatario_id = request.args.get("com", type=int)
    grupo_id = request.args.get("grupo", type=int)

    query = ChatMessage.query
    if grupo_id:
        GrupoChat.query.get_or_404(grupo_id)
        if not _sou_membro(grupo_id) and not current_user.is_admin:
            return jsonify({"error": "Você não participa deste grupo."}), 403
        query = query.filter(ChatMessage.grupo_id == grupo_id)
    elif destinatario_id:
        outro = User.query.get_or_404(destinatario_id)
        query = query.filter(
            or_(
                and_(ChatMessage.user_id == current_user.id, ChatMessage.destinatario_id == outro.id),
                and_(ChatMessage.user_id == outro.id, ChatMessage.destinatario_id == current_user.id),
            )
        )
    else:
        query = query.filter(ChatMessage.destinatario_id.is_(None), ChatMessage.grupo_id.is_(None))

    mensagens = query.order_by(ChatMessage.created_at.desc()).limit(MAX_MENSAGENS).all()
    mensagens.reverse()
    return jsonify([
        m.to_dict(current_user_id=current_user.id, is_admin=current_user.is_admin)
        for m in mensagens
    ])


@api_bp.post("/chat/mensagens")
@aprovado_required
@limiter.limit("30 per minute")
def enviar_mensagem():
    payload = request.get_json(silent=True) or {}
    try:
        data = ChatMensagemIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    destinatario_id = None
    grupo_id = None

    if data.grupoId:
        GrupoChat.query.get_or_404(data.grupoId)
        if not _sou_membro(data.grupoId) and not current_user.is_admin:
            return jsonify({"error": "Você não participa deste grupo."}), 403
        grupo_id = data.grupoId
    elif data.destinatarioId:
        destinatario = User.query.get(data.destinatarioId)
        if destinatario is None:
            return jsonify({"error": "Destinatário não encontrado."}), 404
        if destinatario.id == current_user.id:
            return jsonify({"error": "Você não pode enviar uma mensagem privada para si mesmo."}), 400
        destinatario_id = destinatario.id

    mensagem = ChatMessage(
        user_id=current_user.id, destinatario_id=destinatario_id, grupo_id=grupo_id,
        conteudo=data.conteudo,
    )
    db.session.add(mensagem)
    db.session.commit()
    return jsonify(mensagem.to_dict(current_user_id=current_user.id, is_admin=current_user.is_admin)), 201


@api_bp.put("/chat/mensagens/<int:mensagem_id>")
@aprovado_required
@limiter.limit("30 per minute")
def editar_mensagem(mensagem_id):
    mensagem = ChatMessage.query.get_or_404(mensagem_id)
    if mensagem.user_id != current_user.id:
        return jsonify({"error": "Você só pode editar suas próprias mensagens."}), 403

    payload = request.get_json(silent=True) or {}
    try:
        data = ChatMensagemIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    mensagem.conteudo = data.conteudo
    mensagem.editado_em = utcnow()
    db.session.commit()
    return jsonify(mensagem.to_dict(current_user_id=current_user.id, is_admin=current_user.is_admin))


@api_bp.delete("/chat/mensagens/<int:mensagem_id>")
@aprovado_required
@limiter.limit("30 per minute")
def excluir_mensagem(mensagem_id):
    mensagem = ChatMessage.query.get_or_404(mensagem_id)
    # Numa conversa privada ou de grupo, o admin do SISTEMA não tem poder
    # de moderação automático — só quem é dono da mensagem, exceto no chat
    # geral (público a todos) onde o admin pode remover conteúdo impróprio.
    pode_admin_apagar = current_user.is_admin and mensagem.destinatario_id is None and mensagem.grupo_id is None
    if mensagem.user_id != current_user.id and not pode_admin_apagar:
        return jsonify({"error": "Você não tem permissão para apagar esta mensagem."}), 403

    # Ver comentário equivalente em app/api/avisos.py sobre por que
    # deletar por condição (Core) em vez de session.delete(obj) importa
    # sob concorrência (ex.: apagar duas vezes rapidamente/duas abas).
    linhas_apagadas = ChatMessage.query.filter_by(id=mensagem_id).delete(synchronize_session=False)
    db.session.commit()
    if linhas_apagadas == 0:
        return jsonify({"error": "Esta mensagem já havia sido apagada."}), 404
    return jsonify({"message": "Mensagem apagada."})
