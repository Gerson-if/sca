import os
from datetime import timedelta
from dotenv import load_dotenv

basedir = os.path.abspath(os.path.dirname(__file__))
load_dotenv(os.path.join(basedir, ".env"))


def _bool(val, default=False):
    if val is None:
        return default
    return str(val).lower() in ("1", "true", "yes", "on")


class Config:
    """
    Configuração única, controlada por variáveis de ambiente (.env opcional).

    Por padrão, roda 100% em SQLite e sem nenhuma variável definida — ótimo
    para testar/rodar localmente com um único comando. Para produção, defina
    DATABASE_URL (Postgres), SECRET_KEY e as flags de HTTPS no .env.
    """

    # --- Segurança / chaves ---
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-troque-em-producao")
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    # --- Banco de dados ---
    # Zero-config: SQLite em um arquivo na raiz do projeto (app.db).
    # Produção: defina DATABASE_URL=postgresql+psycopg2://usuario:senha@host:5432/banco
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(basedir, "app.db")
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # pool_pre_ping evita "servir" uma conexão morta do pool (comum atrás
    # de load balancers/proxies de banco que fecham conexões ociosas).
    # pool_recycle fecha conexões antes que o próprio Postgres/gerenciador
    # as derrube por inatividade (bancos gerenciados costumam ter esse
    # limite). pool_size/max_overflow ficam configuráveis por ambiente:
    # sob mais tráfego concorrente, aumente-os junto com GUNICORN_WORKERS
    # (o total de conexões abertas no Postgres é, no pior caso,
    # workers × (pool_size + max_overflow) — ver README, seção Deploy).
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": int(os.environ.get("DB_POOL_RECYCLE", 280)),
        "pool_size": int(os.environ.get("DB_POOL_SIZE", 10)),
        "max_overflow": int(os.environ.get("DB_MAX_OVERFLOW", 20)),
    }

    # --- Flask-Login ---
    # Usados quando a pessoa marca "Lembrar usuário e senha" no login (ver
    # app/auth/routes.py: login_user(..., remember=data.lembrar)). Só é
    # emitido quando ela pede explicitamente — nunca por padrão — então o
    # risco de vazar sessão em navegador/link compartilhado fica sob
    # controle de quem opta pelo recurso, não automático para todo mundo.
    REMEMBER_COOKIE_DURATION = timedelta(days=7)
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)

    # --- Flask-Session (sessão do lado do servidor) ---
    # 'filesystem' funciona out-of-the-box (inclusive com vários workers do
    # Gunicorn, pois compartilham o mesmo disco). Use 'redis' apenas se
    # quiser escalar em múltiplas máquinas.
    SESSION_TYPE = os.environ.get("SESSION_TYPE", "filesystem")
    SESSION_PERMANENT = True
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_FILE_DIR = os.path.join(basedir, ".flask_session")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_REDIS = None  # setado em runtime se SESSION_TYPE=redis (ver app/__init__.py)
    SESSION_COOKIE_SECURE = _bool(os.environ.get("SESSION_COOKIE_SECURE"), False)
    # Assina o identificador de sessão guardado no cookie (com SECRET_KEY),
    # para que não seja possível adivinhar/forjar um ID de sessão válido.
    SESSION_USE_SIGNER = True

    # --- Flask-Caching ---
    # 'SimpleCache' (em memória) é o suficiente para um único processo/worker.
    CACHE_TYPE = os.environ.get("CACHE_TYPE", "SimpleCache")
    CACHE_DEFAULT_TIMEOUT = int(os.environ.get("CACHE_DEFAULT_TIMEOUT", 30))
    CACHE_REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/1")

    # --- Flask-Limiter (rate limiting) ---
    # 'memory://' funciona sem nenhuma dependência externa (ideal p/ 1 worker).
    RATELIMIT_STORAGE_URI = os.environ.get("REDIS_URL", "memory://")
    RATELIMIT_DEFAULT = "200 per hour"
    RATELIMIT_HEADERS_ENABLED = True

    # --- Upload de imagens (Pillow) ---
    UPLOAD_FOLDER = os.path.join(basedir, "app", "static", "uploads")
    MAX_CONTENT_LENGTH = 25 * 1024 * 1024  # 25 MB (cobre imagem + vídeo de fundo)
    ALLOWED_IMAGE_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}
    IMAGE_MAX_DIMENSION = 1600  # px, redimensiona imagens maiores

    # --- Upload de vídeo (fundo animado da landing page) ---
    ALLOWED_VIDEO_EXTENSIONS = {"mp4", "webm"}
    MAX_VIDEO_SIZE = 20 * 1024 * 1024  # 20 MB

    # --- Flask-Talisman (headers de segurança / HTTPS) ---
    # Deixe False para rodar em HTTP simples (ex.: atrás de um proxy que já
    # faz TLS, ou em ambiente local). Ative em produção com HTTPS de verdade.
    TALISMAN_FORCE_HTTPS = _bool(os.environ.get("TALISMAN_FORCE_HTTPS"), False)

    DEBUG = _bool(os.environ.get("FLASK_DEBUG"), False)
    TESTING = False


class TestingConfig(Config):
    """Usada apenas por testes automatizados (pytest)."""

    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"
    # SQLite em memória usa StaticPool, que não aceita pool_size/
    # max_overflow (opções específicas de pools de conexão "de verdade",
    # como o do Postgres em produção — ver Config acima). Herdar
    # SQLALCHEMY_ENGINE_OPTIONS sem sobrescrever isso quebra a criação do
    # engine e impede QUALQUER teste automatizado de rodar.
    SQLALCHEMY_ENGINE_OPTIONS = {}
    RATELIMIT_ENABLED = False
    # Sessão do lado do servidor em memória, isolada por processo de teste
    # — nada de deixar arquivos de sessão de teste no disco do projeto.
    SESSION_TYPE = "filesystem"
    SESSION_FILE_DIR = "/tmp/sca-flask-session-tests"
