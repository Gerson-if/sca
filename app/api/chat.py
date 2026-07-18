from flask import jsonify, request
from flask_login import current_user
from pydantic import ValidationError
from sqlalchemy import and_, or_

from app.api import api_bp
from app.auth.decorators import aprovado_required
from app.extensions import db, limiter
from app.models import ChatMessage, User, utcnow
from app.schemas import ChatMensagemIn

MAX_MENSAGENS = 200


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


@api_bp.get("/chat/mensagens")
@aprovado_required
def listar_mensagens():
    """Retorna as últimas mensagens (mais antigas primeiro), pronto para
    ser exibido direto na tela — o front faz polling simples nesta rota.

    Sem `?com=`, retorna o chat geral (visível a todos). Com `?com=<id>`,
    retorna só a conversa privada entre a pessoa logada e esse usuário —
    nunca mensagens privadas de outras duplas, mesmo para o admin.
    """
    destinatario_id = request.args.get("com", type=int)

    query = ChatMessage.query
    if destinatario_id:
        outro = User.query.get_or_404(destinatario_id)
        query = query.filter(
            or_(
                and_(ChatMessage.user_id == current_user.id, ChatMessage.destinatario_id == outro.id),
                and_(ChatMessage.user_id == outro.id, ChatMessage.destinatario_id == current_user.id),
            )
        )
    else:
        query = query.filter(ChatMessage.destinatario_id.is_(None))

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
    if data.destinatarioId:
        destinatario = User.query.get(data.destinatarioId)
        if destinatario is None:
            return jsonify({"error": "Destinatário não encontrado."}), 404
        if destinatario.id == current_user.id:
            return jsonify({"error": "Você não pode enviar uma mensagem privada para si mesmo."}), 400
        destinatario_id = destinatario.id

    mensagem = ChatMessage(user_id=current_user.id, destinatario_id=destinatario_id, conteudo=data.conteudo)
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
    # Numa conversa privada, o admin não tem poder de moderação sobre
    # mensagens alheias — é uma conversa entre duas pessoas, não pública.
    pode_admin_apagar = current_user.is_admin and mensagem.destinatario_id is None
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
