#!/usr/bin/env bash
# Sobe o SCA localmente com um único comando: cria venv (se preciso),
# instala dependências, aplica migrations no SQLite, popula dados de
# exemplo e inicia o servidor de desenvolvimento.
#
# Uso:
#   ./setup.sh
set -e
cd "$(dirname "$0")"

if [ ! -d ".venv" ]; then
    echo "==> Criando ambiente virtual (.venv)..."
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

echo "==> Instalando dependências..."
pip install -q --upgrade pip
pip install -q -r requirements.txt

export FLASK_APP=wsgi.py

echo "==> Aplicando migrations (SQLite: app.db)..."
flask db upgrade

echo "==> Populando dados de exemplo (idempotente)..."
flask seed-db

echo ""
echo "======================================================"
echo " Tudo pronto! Acesse: http://localhost:5000"
echo " Login padrão: admin / admin123"
echo " Troque a senha com: flask create-admin"
echo "======================================================"
echo ""

flask run --host 0.0.0.0 --port 5000
