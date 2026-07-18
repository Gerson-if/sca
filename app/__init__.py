import os

from flask import Flask, jsonify, request
from flask_talisman import Talisman
from werkzeug.middleware.proxy_fix import ProxyFix

from config import Config, TestingConfig
from app.extensions import db, migrate, login_manager, cache, sess, csrf, limiter


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.config.from_object(TestingConfig if testing else Config)

    _init_proxy_fix(app)
    _init_extensions(app)
    _register_blueprints(app)
    _register_error_handlers(app)
    _register_cli(app)
    _register_security_headers(app)
    _register_session_guard(app)

    return app


def _init_proxy_fix(app: Flask) -> None:
    # Quando a aplicação roda atrás de um proxy reverso (Nginx, Render,
    # Railway, Cloudflare, etc.), o Flask por padrão só enxerga o IP do
    # próprio proxy — não o do visitante de verdade. Isso enfraquece duas
    # defesas importantes: a proteção "strong" de sessão do Flask-Login
    # (que usa IP + user-agent para detectar uma sessão sendo usada de um
    # lugar diferente) e o rate limiting por IP do Flask-Limiter (que sem
    # isso trata todo mundo atrás do proxy como um único cliente).
    #
    # Só habilitamos isso quando TRUST_PROXY_HEADERS=true estiver definido
    # explicitamente no ambiente — nunca por padrão, porque confiar em
    # X-Forwarded-* de uma fonte não controlada permite falsificar o IP de
    # origem. Ative apenas quando você tiver certeza de que só o seu proxy
    # confiável consegue falar diretamente com o processo Flask/Gunicorn.
    if os.environ.get("TRUST_PROXY_HEADERS", "").lower() in ("1", "true", "yes", "on"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1, x_prefix=1)


def _init_extensions(app: Flask) -> None:
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    cache.init_app(app)
    _configurar_sqlite_para_concorrencia(app)

    # Sessão do lado do servidor (Flask-Session). 'filesystem' (padrão) não
    # exige nada além de um diretório em disco; 'redis' é opcional para quem
    # quiser escalar em várias máquinas.
    if app.config.get("SESSION_TYPE") == "redis":
        import redis

        app.config["SESSION_REDIS"] = redis.from_url(
            os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        )
    else:
        os.makedirs(app.config["SESSION_FILE_DIR"], exist_ok=True)
    sess.init_app(app)

    csrf.init_app(app)
    limiter.init_app(app)

    # Flask-Talisman: cabeçalhos de segurança (CSP, HSTS, X-Frame-Options, etc.)
    # O JS/CSS da aplicação agora vive em arquivos estáticos próprios
    # (self), então não precisamos de 'unsafe-inline' para script-src.
    # 'unsafe-eval' é necessário porque o Alpine.js avalia expressões dos
    # atributos (x-show, x-text, etc.) usando `new Function(...)`.
    csp = {
        "default-src": "'self'",
        "script-src": [
            "'self'",
            "'unsafe-eval'",
            "https://cdn.tailwindcss.com",
            "https://cdn.jsdelivr.net",
        ],
        "style-src": ["'self'", "'unsafe-inline'", "https://fonts.googleapis.com", "https://cdnjs.cloudflare.com"],
        "font-src": ["'self'", "https://fonts.gstatic.com", "https://cdnjs.cloudflare.com"],
        "img-src": ["'self'", "data:"],
        "connect-src": "'self'",
    }
    Talisman(
        app,
        force_https=app.config.get("TALISMAN_FORCE_HTTPS", False),
        content_security_policy=csp,
        session_cookie_secure=app.config.get("SESSION_COOKIE_SECURE", False),
    )

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return db.session.get(User, int(user_id))

    @login_manager.unauthorized_handler
    def unauthorized():
        # API pura: nunca redireciona para uma página de login (não existe
        # renderizada pelo servidor); sempre responde em JSON.
        return jsonify({"error": "É necessário autenticar-se."}), 401


def _register_blueprints(app: Flask) -> None:
    from app.main import main_bp
    from app.auth import auth_bp
    from app.api import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(api_bp)


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(400)
    def bad_request(e):
        return jsonify({"error": "Requisição inválida."}), 400

    @app.errorhandler(401)
    def unauthorized(e):
        return jsonify({"error": "É necessário autenticar-se."}), 401

    @app.errorhandler(403)
    def forbidden(e):
        return jsonify({"error": "Acesso negado."}), 403

    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"error": "Recurso não encontrado."}), 404

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "Arquivo excede o tamanho máximo permitido."}), 413

    @app.errorhandler(429)
    def rate_limited(e):
        return jsonify({"error": "Muitas requisições. Tente novamente em instantes."}), 429

    @app.errorhandler(500)
    def server_error(e):
        # Essencial para concorrência: se a transação atual ficou em um
        # estado de erro (ex.: uma IntegrityError não tratada em algum
        # lugar), a conexão volta pro pool do jeito que está. A próxima
        # requisição que pegar essa MESMA conexão do pool herdaria uma
        # transação já quebrada, e falharia de um jeito confuso, sem
        # relação aparente com o que ela mesma está fazendo. Desfazer aqui
        # garante que cada requisição comece com uma transação limpa.
        db.session.rollback()
        return jsonify({"error": "Erro interno no servidor."}), 500

    @app.errorhandler(Exception)
    def unhandled_exception(e):
        # Rede de segurança para qualquer exceção que não vira uma
        # HTTPException conhecida (bug não previsto, erro de terceiros
        # etc.) — mesmo raciocínio do handler de 500 acima: desfaz a
        # transação antes de responder, e loga o erro de verdade (em vez
        # de a pessoa só ver "Erro interno no servidor" sem contexto nos
        # logs do servidor).
        from werkzeug.exceptions import HTTPException

        if isinstance(e, HTTPException):
            return e
        db.session.rollback()
        app.logger.exception("Erro não tratado: %s", e)
        return jsonify({"error": "Erro interno no servidor."}), 500

    from flask_wtf.csrf import CSRFError

    @app.errorhandler(CSRFError)
    def csrf_error(e):
        db.session.rollback()
        return jsonify({"error": "Sessão expirada ou token de segurança inválido. Recarregue a página."}), 400


def _register_security_headers(app: Flask) -> None:
    @app.after_request
    def no_store_dynamic_responses(response):
        # Defesa em profundidade — e a correção do vazamento relatado:
        # NENHUMA resposta dinâmica pode ser guardada em cache por
        # navegador, proxy reverso, CDN ou qualquer camada intermediária.
        #
        # O motivo: o Flask reemite o cookie de sessão (Set-Cookie) em
        # praticamente toda resposta autenticada, inclusive na página
        # principal "/" — que é justamente a URL que é compartilhada entre
        # pessoas. Se ALGO no caminho guardar essa resposta específica (com
        # o Set-Cookie de quem a gerou) e devolvê-la para outra pessoa, essa
        # segunda pessoa recebe o cookie de sessão da primeira e aparece
        # "logada" como ela — foi exatamente esse o comportamento relatado.
        #
        # A correção anterior só cobria "/api/*"; isso deixava "/" (a
        # página principal, o link que de fato é compartilhado) vulnerável.
        # Agora cobrimos TUDO, exceto os arquivos estáticos versionados
        # (/static/*), que não carregam sessão e podem continuar cacheáveis
        # normalmente por performance.
        if not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, private"
            response.headers["Pragma"] = "no-cache"
            response.headers["Vary"] = "Cookie"
        return response


def _configurar_sqlite_para_concorrencia(app: Flask) -> None:
    """Só tem efeito quando o banco é SQLite (dev, ou produção pequena sem
    Postgres) — em Postgres isso não roda.

    Por padrão, o SQLite usa um modo de journal que bloqueia o arquivo
    INTEIRO durante uma escrita, inclusive para quem só está lendo — sob
    múltiplos usuários/threads simultâneos (ver gunicorn.conf.py, worker
    'gthread'), isso vira "database is locked" com frequência. Duas
    mudanças resolvem a grande maioria dos casos:
      - WAL (Write-Ahead Log): leituras não ficam mais bloqueadas por uma
        escrita em andamento.
      - busy_timeout: se ainda assim houver um lock momentâneo (duas
        escritas ao mesmo tempo), a conexão espera alguns segundos antes
        de falhar, em vez de estourar erro imediatamente.
    """
    from sqlalchemy import event

    if not app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        return

    with app.app_context():
        engine = db.engine

        @event.listens_for(engine, "connect")
        def _ativar_wal(conexao_dbapi, _registro_conexao):
            cursor = conexao_dbapi.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()


def _register_session_guard(app: Flask) -> None:
    """Segunda camada de validação de sessão, independente do cookie —
    ver app/auth/guard.py e o docstring de SessaoUsuario em app/models.py.
    """
    from app.auth.guard import registrar_guard_de_sessao

    registrar_guard_de_sessao(app)


def _register_cli(app: Flask) -> None:
    """Comandos: `flask create-admin` e `flask seed-db`."""

    @app.cli.command("create-admin")
    def create_admin():
        import getpass
        from app.models import User, RoleUsuario, StatusUsuario

        username = input("Usuário admin: ").strip()
        password = getpass.getpass("Senha: ")
        if not username or not password:
            print("Usuário e senha são obrigatórios.")
            return
        existente = User.query.filter_by(username=username).first()
        if existente:
            existente.role = RoleUsuario.admin
            existente.status = StatusUsuario.aprovado
            existente.set_password(password)
            db.session.commit()
            print(f"Usuário '{username}' já existia e foi promovido a administrador.")
            return
        user = User(username=username, role=RoleUsuario.admin, status=StatusUsuario.aprovado)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"Usuário administrador '{username}' criado com sucesso.")

    @app.cli.command("ensure-admin")
    def ensure_admin():
        """Cria (ou promove) um administrador de forma NÃO interativa, lendo
        ADMIN_USERNAME / ADMIN_PASSWORD do ambiente. Feito para bootstrap
        automatizado em produção (ex.: entrypoint.sh) — ao contrário de
        `create-admin`, não pede input no terminal, e é seguro rodar toda
        vez que a aplicação sobe: se já existir algum admin, não faz nada.
        """
        import os
        from app.models import User, RoleUsuario, StatusUsuario

        if User.query.filter_by(role=RoleUsuario.admin).first():
            print("Já existe pelo menos um administrador — nada a fazer.")
            return

        username = os.environ.get("ADMIN_USERNAME")
        password = os.environ.get("ADMIN_PASSWORD")
        if not username or not password:
            print(
                "Nenhum admin encontrado e ADMIN_USERNAME/ADMIN_PASSWORD não "
                "foram definidos — pulando (rode 'flask create-admin' manualmente)."
            )
            return

        existente = User.query.filter_by(username=username).first()
        if existente:
            existente.role = RoleUsuario.admin
            existente.status = StatusUsuario.aprovado
            existente.set_password(password)
            db.session.commit()
            print(f"Usuário '{username}' promovido a administrador.")
            return

        admin = User(username=username, role=RoleUsuario.admin, status=StatusUsuario.aprovado)
        admin.set_password(password)
        db.session.add(admin)
        db.session.commit()
        print(f"Administrador '{username}' criado com sucesso.")

    @app.cli.command("seed-db")
    def seed_db():
        from seed import run_seed

        run_seed()
        print("Banco de dados populado com os dados de exemplo.")
