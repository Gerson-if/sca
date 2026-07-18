from flask import Blueprint

api_bp = Blueprint("api", __name__, url_prefix="/api")

from app.api import cidades, avisos, uploads, chat, weather, admin_users, configuracao, sync  # noqa: E402,F401
