from datetime import datetime, timezone

from flask import jsonify, request
from flask_login import current_user
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.api import api_bp
from app.auth.decorators import admin_required
from app.extensions import db, limiter
from app.models import User, StatusUsuario, SessaoUsuario, RoleUsuario
from app.schemas import UsuarioAdminIn, NovoUsuarioAdminIn


def _revogar_sessoes_de(user_id: int) -> None:
    """Derruba imediatamente todas as sessões ativas de um usuário.

    Usado quando o admin reprova, edita a senha, ou exclui alguém: sem
    isso, quem já estava logado continuaria com acesso válido até a sessão
    expirar sozinha (até 8h depois), mesmo sem poder logar de novo — a
    validação em app/auth/guard.py é o que torna essa revogação efetiva
    imediatamente, e não só "na próxima vez que tentar logar".
    """
    SessaoUsuario.query.filter(
        SessaoUsuario.user_id == user_id, SessaoUsuario.revoked_at.is_(None)
    ).update({"revoked_at": datetime.now(timezone.utc)}, synchronize_session=False)


@api_bp.get("/admin/usuarios")
@admin_required
def listar_usuarios():
    status_filtro = request.args.get("status")
    query = User.query.order_by(User.created_at.desc())
    if status_filtro in ("pendente", "aprovado", "reprovado"):
        query = query.filter_by(status=StatusUsuario(status_filtro))
    return jsonify([u.to_dict() for u in query.all()])


@api_bp.post("/admin/usuarios")
@admin_required
@limiter.limit("30 per minute")
def criar_usuario():
    """Admin cria um cadastro diretamente — já nasce aprovado (pula a fila
    de aprovação) e pode nascer com papel de administrador."""
    payload = request.get_json(silent=True) or {}
    try:
        data = NovoUsuarioAdminIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    if User.query.filter_by(username=data.username).first():
        return jsonify({"error": "Esse nome de usuário já está em uso."}), 409

    user = User(
        username=data.username,
        role=RoleUsuario(data.role),
        status=StatusUsuario.aprovado,
    )
    user.set_password(data.password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Duas requisições de criação com o mesmo username em paralelo —
        # a checagem acima não fecha essa janela sozinha; a constraint
        # UNIQUE do banco é a garantia real.
        db.session.rollback()
        return jsonify({"error": "Esse nome de usuário já está em uso."}), 409
    return jsonify(user.to_dict()), 201


@api_bp.post("/admin/usuarios/<int:user_id>/aprovar")
@admin_required
@limiter.limit("60 per minute")
def aprovar_usuario(user_id):
    user = User.query.get_or_404(user_id)
    user.status = StatusUsuario.aprovado
    db.session.commit()
    return jsonify(user.to_dict())


@api_bp.post("/admin/usuarios/<int:user_id>/reprovar")
@admin_required
@limiter.limit("60 per minute")
def reprovar_usuario(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        return jsonify({"error": "Não é possível reprovar um administrador."}), 400
    user.status = StatusUsuario.reprovado
    _revogar_sessoes_de(user.id)
    db.session.commit()
    return jsonify(user.to_dict())


@api_bp.put("/admin/usuarios/<int:user_id>")
@admin_required
@limiter.limit("60 per minute")
def editar_usuario(user_id):
    user = User.query.get_or_404(user_id)
    payload = request.get_json(silent=True) or {}
    try:
        data = UsuarioAdminIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    if data.username and data.username != user.username:
        if User.query.filter_by(username=data.username).first():
            return jsonify({"error": "Esse nome de usuário já está em uso."}), 409
        user.username = data.username

    if data.password:
        user.set_password(data.password)
        # Trocar a senha deve invalidar sessões já abertas com a senha antiga.
        _revogar_sessoes_de(user.id)

    if data.role and RoleUsuario(data.role) != user.role:
        if user.id == current_user.id:
            return jsonify({"error": "Você não pode alterar seu próprio papel."}), 400
        if user.is_admin and data.role == "usuario":
            # Rebaixando um admin: nunca pode deixar o sistema sem nenhum
            # admin. with_for_update() trava as linhas de admin durante
            # esta transação — sem isso, duas requisições rebaixando dois
            # admins diferentes ao mesmo tempo poderiam cada uma contar
            # "ainda tem outro admin" e as duas passarem, zerando os
            # admins do sistema. (SQLite não tem escrita concorrente real,
            # então isso só faz diferença de fato em Postgres.)
            outros_admins = len(
                User.query.with_for_update()
                .filter(User.role == RoleUsuario.admin, User.id != user.id)
                .all()
            )
            if outros_admins == 0:
                db.session.rollback()
                return jsonify({"error": "Não é possível rebaixar o último administrador do sistema."}), 400
        user.role = RoleUsuario(data.role)
        if user.role == RoleUsuario.admin:
            user.status = StatusUsuario.aprovado

    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        return jsonify({"error": "Esse nome de usuário já está em uso."}), 409
    return jsonify(user.to_dict())


@api_bp.delete("/admin/usuarios/<int:user_id>")
@admin_required
@limiter.limit("30 per minute")
def excluir_usuario(user_id):
    user = User.query.get_or_404(user_id)
    if user.is_admin:
        return jsonify({"error": "Não é possível excluir um administrador."}), 400
    if user.id == current_user.id:
        return jsonify({"error": "Você não pode excluir a si mesmo."}), 400

    from app.models import ChatMessage

    nome = user.username
    ChatMessage.query.filter_by(user_id=user.id).update({"user_id": None})
    SessaoUsuario.query.filter_by(user_id=user.id).delete()
    # Ver comentário equivalente em app/api/avisos.py sobre por que
    # deletar por condição (Core) em vez de session.delete(obj) importa
    # sob concorrência (ex.: dois cliques de "excluir" quase simultâneos).
    linhas_apagadas = User.query.filter_by(id=user_id).delete(synchronize_session=False)
    db.session.commit()
    if linhas_apagadas == 0:
        return jsonify({"error": "Este usuário já havia sido excluído."}), 404
    return jsonify({"message": f'Usuário "{nome}" removido com sucesso.'})
