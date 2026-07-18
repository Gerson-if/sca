from functools import wraps

from flask import jsonify
from flask_login import current_user, login_required


def admin_required(f):
    """Só permite acesso a usuários com role == admin."""

    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            return jsonify({"error": "Acesso restrito ao administrador."}), 403
        return f(*args, **kwargs)

    return wrapper


def aprovado_required(f):
    """Permite acesso a admins e a usuários comuns já aprovados pelo admin.
    Usuários pendentes/reprovados são bloqueados mesmo estando logados."""

    @wraps(f)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.pode_acessar:
            return jsonify({"error": "Seu cadastro ainda não foi aprovado pelo administrador."}), 403
        return f(*args, **kwargs)

    return wrapper
