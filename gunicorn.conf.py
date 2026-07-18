"""Configuração do Gunicorn (produção).
Uso: gunicorn -c gunicorn.conf.py wsgi:app
"""
import os

bind = os.environ.get("GUNICORN_BIND", "0.0.0.0:" + os.environ.get("PORT", "8000"))

# 'gthread' é o que faz o `threads` abaixo funcionar: o worker padrão do
# Gunicorn ('sync') atende UMA requisição por vez, ignorando `threads`
# silenciosamente (sem erro, sem aviso) — o valor ficava configurado sem
# nenhum efeito. Com 'gthread', cada worker atende várias requisições
# concorrentes (I/O-bound: banco, upload, chamadas externas de clima etc.)
# em paralelo, o que é essencial para múltiplos usuários simultâneos.
worker_class = os.environ.get("GUNICORN_WORKER_CLASS", "gthread")

# Padrão enxuto (2 workers x 4 threads): bom o suficiente para SQLite +
# tráfego pequeno/médio. Se migrar para PostgreSQL e precisar de mais
# capacidade, aumente GUNICORN_WORKERS e configure REDIS_URL (para
# cache/sessão/rate-limit compartilhados entre os processos) — e ajuste
# DB_POOL_SIZE/DB_MAX_OVERFLOW (config.py) de acordo, já que o total de
# conexões abertas no Postgres é, no pior caso,
# workers × (pool_size + max_overflow).
workers = int(os.environ.get("GUNICORN_WORKERS", 2))
threads = int(os.environ.get("GUNICORN_THREADS", 4))
timeout = int(os.environ.get("GUNICORN_TIMEOUT", 30))
graceful_timeout = 30
keepalive = 5

# Descarta e reinicia um worker periodicamente (com variação aleatória
# para não derrubar todos ao mesmo tempo) — protege contra vazamento de
# memória lento se acumular ao longo de muitos dias no ar.
max_requests = int(os.environ.get("GUNICORN_MAX_REQUESTS", 2000))
max_requests_jitter = int(os.environ.get("GUNICORN_MAX_REQUESTS_JITTER", 200))

accesslog = "-"   # stdout
errorlog = "-"    # stderr
loglevel = os.environ.get("GUNICORN_LOG_LEVEL", "info")

forwarded_allow_ips = "*"
