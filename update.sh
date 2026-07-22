#!/usr/bin/env bash
# ============================================================================
# SCA — Atualização segura de produção
# ============================================================================
# Atualiza o SCA já instalado por deploy.sh sem risco de derrubar o site:
# faz backup do banco antes de mexer em qualquer coisa, atualiza o código e
# as dependências, aplica migrations, reinicia o serviço e CONFIRMA que a
# aplicação respondeu OK. Se qualquer etapa falhar, desfaz tudo sozinho e
# deixa o site rodando na versão anterior.
#
# Uso:
#   sudo ./update.sh
# ============================================================================
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

CONF_FILE="$APP_DIR/deploy/.deploy.conf"
[ -f "$CONF_FILE" ] || {
    echo "Não encontrei $CONF_FILE — este servidor não parece ter sido instalado com deploy.sh."
    echo "Rode ./deploy.sh primeiro (ou ajuste as variáveis SERVICE_NAME/PORT manualmente no topo deste script)."
    exit 1
}
# shellcheck source=/dev/null
source "$CONF_FILE"

C_RESET="\033[0m"; C_BOLD="\033[1m"; C_GREEN="\033[32m"; C_YELLOW="\033[33m"; C_RED="\033[31m"; C_BLUE="\033[36m"
log()  { echo -e "${C_BLUE}==>${C_RESET} ${C_BOLD}$*${C_RESET}"; }
ok()   { echo -e "${C_GREEN}✔${C_RESET} $*"; }
warn() { echo -e "${C_YELLOW}⚠${C_RESET} $*"; }
err()  { echo -e "${C_RED}✘ $*${C_RESET}"; }

[ "$(id -u)" -eq 0 ] || { err "Rode como root (ex.: sudo ./update.sh)."; exit 1; }

BACKUP_ROOT="$APP_DIR/backups"
STAMP="$(date +%Y%m%d_%H%M%S)"
BACKUP_DIR="$BACKUP_ROOT/$STAMP"
mkdir -p "$BACKUP_DIR"
LOG_FILE="$APP_DIR/update.log"

log_event() { echo "[$(date -Iseconds)] $*" >> "$LOG_FILE"; }

ROLLED_BACK=0
rollback() {
    [ "$ROLLED_BACK" = "1" ] && return
    ROLLED_BACK=1
    echo ""
    warn "Revertendo para o estado anterior..."
    log_event "FALHA — iniciando rollback"

    if [ -n "${PREV_COMMIT:-}" ] && git -C "$APP_DIR" rev-parse --git-dir >/dev/null 2>&1; then
        git -C "$APP_DIR" reset --hard "$PREV_COMMIT" >/dev/null 2>&1 || true
        ok "Código revertido para o commit anterior ($PREV_COMMIT)."
    fi

    if [ "$DB_TIPO" = "sqlite" ] && [ -f "$BACKUP_DIR/app.db" ]; then
        cp "$BACKUP_DIR/app.db" "$APP_DIR/app.db"
        ok "Banco SQLite restaurado do backup."
    elif [ "$DB_TIPO" = "postgres" ] && [ -f "$BACKUP_DIR/dump.sql" ]; then
        # shellcheck source=/dev/null
        set -a; source "$APP_DIR/.env"; set +a
        DB_URL="${DATABASE_URL:-}"
        if [ -n "$DB_URL" ] && psql "$DB_URL" < "$BACKUP_DIR/dump.sql" >/dev/null 2>&1; then
            ok "Banco Postgres restaurado do backup."
        else
            warn "Não consegui restaurar o dump automaticamente — restaure manualmente de $BACKUP_DIR/dump.sql"
        fi
    fi

    "$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt" || true
    systemctl restart "$SERVICE_NAME" || true
    sleep 2
    if systemctl is-active --quiet "$SERVICE_NAME"; then
        warn "Atualização cancelada — site restaurado à versão anterior e funcionando."
    else
        err "Atualização cancelada, e o serviço não voltou sozinho. Verifique: journalctl -u $SERVICE_NAME -n 100"
    fi
    log_event "Rollback concluído."
    exit 1
}
trap rollback ERR

echo ""
echo -e "${C_BOLD}============================================================${C_RESET}"
echo -e "${C_BOLD}  SCA — Atualização segura${C_RESET}"
echo -e "${C_BOLD}============================================================${C_RESET}"
log_event "Iniciando atualização."

# ---------------------------------------------------------------------------
# 1) Backup
# ---------------------------------------------------------------------------
log "1/6 — Fazendo backup do banco de dados em $BACKUP_DIR ..."
if [ "$DB_TIPO" = "sqlite" ]; then
    [ -f "$APP_DIR/app.db" ] && cp "$APP_DIR/app.db" "$BACKUP_DIR/app.db"
elif [ "$DB_TIPO" = "postgres" ]; then
    set -a; source "$APP_DIR/.env"; set +a
    if [ -n "${DATABASE_URL:-}" ]; then
        pg_dump "$DATABASE_URL" > "$BACKUP_DIR/dump.sql" 2>/dev/null \
            || warn "pg_dump falhou (verifique se o cliente 'postgresql-client' está instalado) — continuando sem backup de dados."
    fi
fi
cp "$APP_DIR/.env" "$BACKUP_DIR/.env.bak" 2>/dev/null || true
ok "Backup salvo."

# Mantém só os últimos 10 backups
ls -1dt "$BACKUP_ROOT"/*/ 2>/dev/null | tail -n +11 | xargs -r rm -rf
log_event "Backup criado em $BACKUP_DIR"

# ---------------------------------------------------------------------------
# 2) Atualização do código
# ---------------------------------------------------------------------------
log "2/6 — Atualizando o código..."
if git -C "$APP_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    PREV_COMMIT=$(git -C "$APP_DIR" rev-parse HEAD)
    if [ -n "$(git -C "$APP_DIR" status --porcelain)" ]; then
        err "Há alterações locais não commitadas em $APP_DIR — abortando para não perder nada."
        echo "  Revise com 'git status', faça commit/stash, e rode ./update.sh de novo."
        exit 1
    fi
    git -C "$APP_DIR" fetch --quiet
    git -C "$APP_DIR" pull --quiet --ff-only
    NEW_COMMIT=$(git -C "$APP_DIR" rev-parse HEAD)
    if [ "$PREV_COMMIT" = "$NEW_COMMIT" ]; then
        ok "Já estava na versão mais recente ($NEW_COMMIT)."
    else
        ok "Código atualizado: $PREV_COMMIT -> $NEW_COMMIT"
    fi
else
    warn "Este diretório não é um repositório git — pulando atualização de código."
    warn "(Se você atualiza o código por outro meio — ex.: enviando os arquivos por scp/rsync — pode ignorar este aviso.)"
fi

# ---------------------------------------------------------------------------
# 3) Dependências
# ---------------------------------------------------------------------------
log "3/6 — Instalando/atualizando dependências Python..."
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
ok "Dependências em dia."

# ---------------------------------------------------------------------------
# 4) Migrations
# ---------------------------------------------------------------------------
log "4/6 — Aplicando migrations do banco de dados..."
export FLASK_APP=wsgi.py
sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR' && set -a && source .env && set +a &&
    '$APP_DIR/.venv/bin/flask' db upgrade
"
ok "Migrations aplicadas."

# ---------------------------------------------------------------------------
# 5) Reinício do serviço
# ---------------------------------------------------------------------------
log "5/6 — Reiniciando o serviço ($SERVICE_NAME)..."
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
systemctl restart "$SERVICE_NAME"

# ---------------------------------------------------------------------------
# 6) Verificação de saúde
# ---------------------------------------------------------------------------
log "6/6 — Verificando se a aplicação respondeu corretamente..."
HEALTH_OK=0
for _tentativa in $(seq 1 15); do
    if curl -fsS "http://127.0.0.1:${PORT}/healthz" >/dev/null 2>&1; then
        HEALTH_OK=1
        break
    fi
    sleep 1
done

if [ "$HEALTH_OK" != "1" ]; then
    err "A aplicação não respondeu em http://127.0.0.1:${PORT}/healthz após a atualização."
    rollback
fi

trap - ERR
ok "Aplicação respondendo normalmente."
log_event "Atualização concluída com sucesso."

echo ""
echo -e "${C_GREEN}${C_BOLD}============================================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD} Atualização concluída com sucesso!${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}============================================================${C_RESET}"
echo ""
echo "  Backup desta atualização: $BACKUP_DIR"
echo "  Log completo:             $LOG_FILE"
echo "  Status do serviço:        systemctl status $SERVICE_NAME"
echo ""
