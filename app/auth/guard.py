"""Segunda camada de validação de sessão — independente do cookie.

Ver o docstring de `SessaoUsuario` em app/models.py para o motivo desta
verificação existir. Resumo: o Flask-Login/Flask-Session já isola cada
navegador/dispositivo corretamente (testado e confirmado), mas qualquer
camada extra no meio do caminho (proxy, CDN, cache, algum bug futuro) que
por acaso misture ou reaproveite uma resposta entre usuários é pega aqui,
porque validamos a autenticação contra um registro no banco — não confiamos
cegamente no que o cookie/Flask-Login afirmam.
"""

from datetime import datetime, timezone

from flask import session
from flask_login import current_user, logout_user

from app.extensions import db
from app.models import SessaoUsuario


def _utcnow():
    return datetime.now(timezone.utc)


def _as_aware(dt):
    if dt is not None and dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def registrar_guard_de_sessao(app):
    """Registra um before_request global que valida a sessão autenticada.

    Roda em TODA requisição (não só nas rotas com @login_required), porque
    o objetivo é impedir que o Flask-Login sequer considere alguém
    autenticado quando não há um registro de sessão válido correspondente.
    """

    @app.before_request
    def _validar_sessao_autenticada():
        if not current_user.is_authenticated:
            return

        token = session.get("session_token")
        sessao = SessaoUsuario.query.filter_by(token=token).first() if token else None

        sessao_valida = (
            sessao is not None
            and sessao.revoked_at is None
            and str(sessao.user_id) == str(current_user.get_id())
        )
        if not sessao_valida:
            # O Flask-Login diz "autenticado", mas não existe um registro de
            # sessão correspondente (nunca existiu, foi revogado em outro
            # lugar, ou pertence a outro usuário). Nunca confiamos só no
            # cookie nesse caso: encerramos tudo imediatamente. As rotas
            # protegidas por @login_required vão responder 401 normalmente
            # logo em seguida, e o front-end reage exibindo a tela de login.
            logout_user()
            session.clear()
            return

        # Atualiza "último acesso" no máximo 1x por minuto por sessão, para
        # não gerar um UPDATE no banco a cada requisição.
        agora = _utcnow()
        ultimo = _as_aware(sessao.last_seen_at)
        if ultimo is None or (agora - ultimo).total_seconds() > 60:
            sessao.last_seen_at = agora
            db.session.commit()
