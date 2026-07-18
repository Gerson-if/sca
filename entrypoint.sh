#!/usr/bin/env bash
# Bootstrap de PRODUÇÃO (Postgres) — usar isso em vez de `flask run` /
# rodar o gunicorn "na mão" em produção.
#
# O que este script resolve: os comandos de criação de schema (migrations)
# e o primeiro usuário admin, de forma que funcionem de forma confiável
# contra Postgres (e não só contra o SQLite usado em setup.sh/dev), e
# sem quebrar se o Postgres ainda estiver subindo quando o processo da
# aplicação iniciar (comum em orquestradores como Docker Compose/Kubernetes,
# onde o container do app pode iniciar antes do banco aceitar conexões).
#
# Uso:
#   export DATABASE_URL=postgresql+psycopg2://usuario:senha@host:5432/banco
#   export SECRET_KEY=...
#   ./entrypoint.sh
#
# Variáveis opcionais:
#   ADMIN_USERNAME / ADMIN_PASSWORD  -> cria o primeiro admin automaticamente
#                                       (só se ainda não existir nenhum admin)
set -euo pipefail
cd "$(dirname "$0")"

export FLASK_APP=wsgi.py

if [ -z "${DATABASE_URL:-}" ]; then
    echo "AVISO: DATABASE_URL não definido — rodando em SQLite local."
    echo "       Isso NÃO é recomendado em produção (ver README.md, seção Deploy)."
fi

echo "==> Aguardando o banco de dados ficar disponível..."
python3 - <<'PY'
import os
import sys
import time

url = os.environ.get("DATABASE_URL")
if not url:
    sys.exit(0)  # SQLite: nada para esperar

import sqlalchemy

ultimo_erro = None
for tentativa in range(1, 31):
    try:
        engine = sqlalchemy.create_engine(url, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(sqlalchemy.text("SELECT 1"))
        print("Banco de dados disponível.")
        sys.exit(0)
    except Exception as exc:  # noqa: BLE001 — queremos capturar qualquer erro de conexão
        ultimo_erro = exc
        print(f"  tentativa {tentativa}/30: banco ainda não respondeu ({exc.__class__.__name__}); aguardando 2s...")
        time.sleep(2)

print(f"ERRO: não foi possível conectar ao banco de dados após 30 tentativas: {ultimo_erro}")
sys.exit(1)
PY

echo "==> Aplicando migrations (flask db upgrade)..."
# Idempotente: se já estiver tudo aplicado, o Alembic simplesmente não faz
# nada — seguro de rodar em todo boot/deploy, não só na primeira vez.
flask db upgrade

if [ -n "${ADMIN_USERNAME:-}" ] && [ -n "${ADMIN_PASSWORD:-}" ]; then
    echo "==> Garantindo usuário administrador inicial..."
    flask ensure-admin
fi

echo "==> Iniciando Gunicorn..."
exec gunicorn -c gunicorn.conf.py wsgi:app
