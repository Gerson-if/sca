#!/usr/bin/env bash
# ============================================================================
# SCA — Instalador guiado de produção (Ubuntu)
# ============================================================================
# Sobe o SCA inteiro num servidor Ubuntu limpo com UM comando: pacotes do
# sistema, ambiente Python, banco de dados, serviço systemd, Nginx e
# certificado SSL gratuito (ZeroSSL ou Let's Encrypt) — tudo perguntado de
# forma guiada, sem precisar editar nenhum arquivo manualmente.
#
# Uso:
#   sudo ./deploy.sh
#
# Pode ser executado de novo a qualquer momento (ex.: para trocar de domínio,
# ativar SSL depois, ou só corrigir alguma configuração) — as respostas
# anteriores ficam salvas em deploy/.deploy.conf e são sugeridas como padrão.
# ============================================================================
set -euo pipefail

# ---------------------------------------------------------------------------
# Preparação
# ---------------------------------------------------------------------------
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$APP_DIR"

CONF_DIR="$APP_DIR/deploy"
CONF_FILE="$CONF_DIR/.deploy.conf"
mkdir -p "$CONF_DIR"

# shellcheck source=/dev/null
[ -f "$CONF_FILE" ] && source "$CONF_FILE"

C_RESET="\033[0m"; C_BOLD="\033[1m"; C_GREEN="\033[32m"; C_YELLOW="\033[33m"; C_RED="\033[31m"; C_BLUE="\033[36m"

log()   { echo -e "${C_BLUE}==>${C_RESET} ${C_BOLD}$*${C_RESET}"; }
ok()    { echo -e "${C_GREEN}✔${C_RESET} $*"; }
warn()  { echo -e "${C_YELLOW}⚠${C_RESET} $*"; }
fail()  { echo -e "${C_RED}✘ $*${C_RESET}"; exit 1; }

ask() {
    # ask "Pergunta" "valor_padrao" -> ecoa a resposta (ou o padrão) no stdout
    local pergunta="$1" padrao="${2:-}" resposta
    if [ -n "$padrao" ]; then
        read -r -p "$pergunta [$padrao]: " resposta || true
        echo "${resposta:-$padrao}"
    else
        read -r -p "$pergunta: " resposta || true
        echo "$resposta"
    fi
}

ask_password() {
    local pergunta="$1" senha
    read -r -s -p "$pergunta: " senha || true
    echo "" >&2
    echo "$senha"
}

confirm() {
    # confirm "Pergunta" [padrao s/n] -> retorna 0 (sim) ou 1 (não)
    local pergunta="$1" padrao="${2:-s}" resposta
    if [ "$padrao" = "s" ]; then
        read -r -p "$pergunta [S/n]: " resposta || true
        resposta="${resposta:-s}"
    else
        read -r -p "$pergunta [s/N]: " resposta || true
        resposta="${resposta:-n}"
    fi
    [[ "$resposta" =~ ^[sSyY] ]]
}

choose() {
    # choose "Titulo" "opcao1" "opcao2" ... -> imprime o número escolhido (1-based) em stdout
    local titulo="$1"; shift
    local opcoes=("$@")
    echo -e "${C_BOLD}$titulo${C_RESET}" >&2
    local i=1
    for o in "${opcoes[@]}"; do
        echo "  $i) $o" >&2
        i=$((i + 1))
    done
    local escolha
    while true; do
        read -r -p "Escolha [1-${#opcoes[@]}]: " escolha || true
        if [[ "$escolha" =~ ^[0-9]+$ ]] && [ "$escolha" -ge 1 ] && [ "$escolha" -le "${#opcoes[@]}" ]; then
            echo "$escolha"
            return
        fi
        echo "Opção inválida." >&2
    done
}

[ "$(id -u)" -eq 0 ] || fail "Rode este script como root (ex.: sudo ./deploy.sh)."

if ! grep -qi ubuntu /etc/os-release 2>/dev/null; then
    warn "Este script foi feito para Ubuntu. Detectei outro sistema — pode não funcionar perfeitamente."
    confirm "Continuar mesmo assim?" n || exit 1
fi

echo ""
echo -e "${C_BOLD}============================================================${C_RESET}"
echo -e "${C_BOLD}  SCA — Instalador guiado de produção${C_RESET}"
echo -e "${C_BOLD}============================================================${C_RESET}"
echo ""

# ---------------------------------------------------------------------------
# 1) Perguntas
# ---------------------------------------------------------------------------
log "Passo 1/8 — Endereço de acesso"

MODO_ACESSO_OPCOES=("Tenho um domínio (ex.: sca.minhaempresa.com.br) — recomendado, permite SSL" \
                    "Não tenho domínio, vou acessar pelo IP local/da rede — sem SSL (uso interno)")
escolha=$(choose "Como o SCA vai ser acessado?" "${MODO_ACESSO_OPCOES[@]}")

if [ "$escolha" = "1" ]; then
    MODO_ACESSO="dominio"
    DOMINIO=$(ask "Qual o domínio (sem http/https, ex.: sca.minhaempresa.com.br)" "${DOMINIO:-}")
    [ -n "$DOMINIO" ] || fail "Domínio não pode ficar em branco."
else
    MODO_ACESSO="ip"
    IP_PADRAO=$(hostname -I 2>/dev/null | awk '{print $1}')
    SERVER_IP=$(ask "IP deste servidor (usado só para mostrar a URL final)" "${SERVER_IP:-$IP_PADRAO}")
    DOMINIO="_"   # server_name coringa no Nginx
fi

echo ""
log "Passo 2/8 — Certificado SSL"

if [ "$MODO_ACESSO" = "dominio" ]; then
    echo "Antes de continuar, confirme que o DNS do domínio já aponta para o IP deste servidor"
    echo "(sem isso, a emissão do certificado vai falhar)."
    SSL_OPCOES=("ZeroSSL — gratuito, sem cartão de crédito, renovação automática" \
                "Let's Encrypt — gratuito, alternativa mais tradicional, renovação automática" \
                "Sem SSL por enquanto — configuro depois")
    escolha=$(choose "Qual autoridade certificadora usar?" "${SSL_OPCOES[@]}")
    case "$escolha" in
        1) SSL_PROVIDER="zerossl" ;;
        2) SSL_PROVIDER="letsencrypt" ;;
        *) SSL_PROVIDER="nenhum" ;;
    esac
    if [ "$SSL_PROVIDER" != "nenhum" ]; then
        EMAIL_SSL=$(ask "E-mail para avisos de renovação do certificado" "${EMAIL_SSL:-}")
        [ -n "$EMAIL_SSL" ] || fail "E-mail é obrigatório para emitir o certificado."
    fi
else
    SSL_PROVIDER="nenhum"
    warn "Sem domínio não é possível emitir certificado público — o acesso será por HTTP."
fi

echo ""
log "Passo 3/8 — Banco de dados"

DB_OPCOES=("SQLite — zero configuração, ótimo para tráfego pequeno/médio (recomendado)" \
           "PostgreSQL — mais robusto para tráfego alto/vários processos simultâneos")
escolha=$(choose "Qual banco de dados usar?" "${DB_OPCOES[@]}")
if [ "$escolha" = "1" ]; then
    DB_TIPO="sqlite"
else
    DB_TIPO="postgres"
    DB_NOME=$(ask "Nome do banco Postgres" "${DB_NOME:-sca_db}")
    DB_USUARIO=$(ask "Usuário do Postgres" "${DB_USUARIO:-sca_user}")
    if [ -z "${DB_SENHA:-}" ]; then
        DB_SENHA=$(openssl rand -hex 16)
        echo "Gerada automaticamente uma senha forte para o banco (fica salva só no .env do servidor)."
    fi
fi

echo ""
log "Passo 4/8 — Administrador inicial"

ADMIN_USERNAME=$(ask "Usuário do administrador" "${ADMIN_USERNAME:-admin}")
if [ -z "${ADMIN_PASSWORD:-}" ]; then
    if confirm "Gerar automaticamente uma senha forte para o admin?" s; then
        ADMIN_PASSWORD=$(openssl rand -base64 18)
        ADMIN_PASSWORD_GERADA=1
    else
        ADMIN_PASSWORD=$(ask_password "Senha do administrador (mín. 8 caracteres)")
    fi
fi

echo ""
log "Passo 5/8 — Serviço"

APP_USER=$(ask "Usuário do sistema que vai rodar o serviço" "${APP_USER:-sca}")
SERVICE_NAME=$(ask "Nome do serviço systemd" "${SERVICE_NAME:-sca}")
PORT=$(ask "Porta interna do Gunicorn (o Nginx conversa com ela; não precisa abrir no firewall)" "${PORT:-8000}")
GUNICORN_WORKERS=$(ask "Quantos workers do Gunicorn" "${GUNICORN_WORKERS:-2}")

# Salva as respostas já para o caso de o script falhar mais à frente
{
    echo "APP_DIR=\"$APP_DIR\""
    echo "MODO_ACESSO=\"$MODO_ACESSO\""
    echo "DOMINIO=\"$DOMINIO\""
    echo "SERVER_IP=\"${SERVER_IP:-}\""
    echo "SSL_PROVIDER=\"$SSL_PROVIDER\""
    echo "EMAIL_SSL=\"${EMAIL_SSL:-}\""
    echo "DB_TIPO=\"$DB_TIPO\""
    echo "DB_NOME=\"${DB_NOME:-}\""
    echo "DB_USUARIO=\"${DB_USUARIO:-}\""
    echo "APP_USER=\"$APP_USER\""
    echo "SERVICE_NAME=\"$SERVICE_NAME\""
    echo "PORT=\"$PORT\""
    echo "GUNICORN_WORKERS=\"$GUNICORN_WORKERS\""
} > "$CONF_FILE"
chmod 600 "$CONF_FILE"

echo ""
echo -e "${C_BOLD}Resumo:${C_RESET}"
echo "  Acesso .......... $( [ "$MODO_ACESSO" = dominio ] && echo "https://$DOMINIO" || echo "http://${SERVER_IP:-<ip-do-servidor>}" )"
echo "  SSL ............. $SSL_PROVIDER"
echo "  Banco de dados .. $DB_TIPO"
echo "  Serviço ......... $SERVICE_NAME (usuário: $APP_USER, porta interna: $PORT)"
echo ""
confirm "Confirma e inicia a instalação?" s || { echo "Cancelado."; exit 0; }

# ---------------------------------------------------------------------------
# 2) Pacotes do sistema
# ---------------------------------------------------------------------------
echo ""
log "Passo 6/8 — Instalando pacotes do sistema (isso pode levar alguns minutos)..."

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
PACOTES=(python3 python3-venv python3-pip nginx curl git socat ufw)
[ "$DB_TIPO" = "postgres" ] && PACOTES+=(postgresql postgresql-contrib libpq-dev)
[ "$SSL_PROVIDER" = "letsencrypt" ] && PACOTES+=(certbot python3-certbot-nginx)
apt-get install -y -qq "${PACOTES[@]}"
ok "Pacotes instalados."

# Usuário de sistema dedicado (sem shell, sem login) para rodar a aplicação
if ! id "$APP_USER" &>/dev/null; then
    useradd --system --home "$APP_DIR" --shell /usr/sbin/nologin "$APP_USER"
    ok "Usuário de sistema '$APP_USER' criado."
fi

# ---------------------------------------------------------------------------
# 3) Banco de dados (Postgres, se escolhido)
# ---------------------------------------------------------------------------
if [ "$DB_TIPO" = "postgres" ]; then
    log "Configurando PostgreSQL..."
    sudo -u postgres psql -tc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USUARIO'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE USER $DB_USUARIO WITH PASSWORD '$DB_SENHA';"
    sudo -u postgres psql -tc "SELECT 1 FROM pg_database WHERE datname='$DB_NOME'" | grep -q 1 || \
        sudo -u postgres psql -c "CREATE DATABASE $DB_NOME OWNER $DB_USUARIO;"
    sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NOME TO $DB_USUARIO;" >/dev/null
    DATABASE_URL="postgresql+psycopg2://$DB_USUARIO:$DB_SENHA@localhost:5432/$DB_NOME"
    ok "Banco '$DB_NOME' e usuário '$DB_USUARIO' prontos."
fi

# ---------------------------------------------------------------------------
# 4) Ambiente Python
# ---------------------------------------------------------------------------
log "Criando ambiente virtual e instalando dependências..."
python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/requirements.txt"
ok "Dependências instaladas."

# ---------------------------------------------------------------------------
# 5) Arquivo .env
# ---------------------------------------------------------------------------
log "Gerando arquivo .env..."
if [ -f "$APP_DIR/.env" ]; then
    cp "$APP_DIR/.env" "$APP_DIR/.env.bak.$(date +%Y%m%d%H%M%S)"
    warn "Já existia um .env — foi salvo uma cópia de segurança (.env.bak.*)."
    # shellcheck source=/dev/null
    SECRET_KEY_ATUAL=$(grep -m1 '^SECRET_KEY=' "$APP_DIR/.env" | cut -d= -f2- || true)
fi
SECRET_KEY="${SECRET_KEY_ATUAL:-$(openssl rand -hex 32)}"

{
    echo "# Gerado por deploy.sh em $(date -Iseconds)"
    echo "SECRET_KEY=$SECRET_KEY"
    [ "$DB_TIPO" = "postgres" ] && echo "DATABASE_URL=$DATABASE_URL"
    echo "ADMIN_USERNAME=$ADMIN_USERNAME"
    echo "ADMIN_PASSWORD=$ADMIN_PASSWORD"
    echo "PORT=$PORT"
    echo "GUNICORN_WORKERS=$GUNICORN_WORKERS"
    echo "TRUST_PROXY_HEADERS=true"
    if [ "$SSL_PROVIDER" != "nenhum" ]; then
        echo "SESSION_COOKIE_SECURE=true"
        echo "TALISMAN_FORCE_HTTPS=true"
    fi
} > "$APP_DIR/.env"
chmod 600 "$APP_DIR/.env"
chown "$APP_USER:$APP_USER" "$APP_DIR/.env"
ok ".env criado."

# Garante que o dono dos arquivos da aplicação é o usuário de serviço
mkdir -p "$APP_DIR/app/static/uploads" "$APP_DIR/.flask_session"
chown -R "$APP_USER:$APP_USER" "$APP_DIR"

# ---------------------------------------------------------------------------
# 6) Migrations + admin
# ---------------------------------------------------------------------------
log "Aplicando migrations e garantindo o usuário administrador..."
export FLASK_APP=wsgi.py
sudo -u "$APP_USER" bash -c "
    cd '$APP_DIR' && set -a && source .env && set +a &&
    '$APP_DIR/.venv/bin/flask' db upgrade &&
    '$APP_DIR/.venv/bin/flask' ensure-admin
"
ok "Banco de dados pronto e administrador garantido."

# ---------------------------------------------------------------------------
# 7) systemd
# ---------------------------------------------------------------------------
log "Configurando o serviço systemd ($SERVICE_NAME)..."
cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=SCA Backend (Gunicorn)
After=network.target $( [ "$DB_TIPO" = "postgres" ] && echo "postgresql.service" )

[Service]
Type=simple
User=$APP_USER
Group=$APP_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/.venv/bin/gunicorn -c gunicorn.conf.py wsgi:app
ExecReload=/bin/kill -s HUP \$MAINPID
Restart=always
RestartSec=3
# Endurecimento básico do serviço
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=full
ProtectHome=true

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME" >/dev/null
systemctl restart "$SERVICE_NAME"
sleep 2
if systemctl is-active --quiet "$SERVICE_NAME"; then
    ok "Serviço '$SERVICE_NAME' rodando."
else
    fail "O serviço não subiu. Veja os logs com: journalctl -u $SERVICE_NAME -n 80 --no-pager"
fi

# ---------------------------------------------------------------------------
# 8) Nginx + SSL
# ---------------------------------------------------------------------------
log "Passo 7/8 — Configurando o Nginx..."

NGINX_SITE="/etc/nginx/sites-available/${SERVICE_NAME}.conf"
WEBROOT_ACME="/var/www/${SERVICE_NAME}-acme"
mkdir -p "$WEBROOT_ACME"

# Primeiro sobe um bloco HTTP simples — necessário para o desafio do
# certificado (HTTP-01) e também serve como fallback se SSL não for usado.
cat > "$NGINX_SITE" <<EOF
upstream ${SERVICE_NAME}_app {
    server 127.0.0.1:$PORT;
}

server {
    listen 80;
    listen [::]:80;
    server_name $DOMINIO;

    location /.well-known/acme-challenge/ {
        root $WEBROOT_ACME;
    }

    location /static/ {
        alias $APP_DIR/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://${SERVICE_NAME}_app;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
        proxy_read_timeout 60s;
        client_max_body_size 26M;
    }
}
EOF

ln -sf "$NGINX_SITE" "/etc/nginx/sites-enabled/${SERVICE_NAME}.conf"
rm -f /etc/nginx/sites-enabled/default
nginx -t && systemctl reload nginx
ok "Nginx configurado em HTTP."

CERT_DIR="/etc/sca-ssl/$DOMINIO"

case "$SSL_PROVIDER" in
    letsencrypt)
        log "Emitindo certificado Let's Encrypt para $DOMINIO..."
        certbot --nginx -d "$DOMINIO" -m "$EMAIL_SSL" --agree-tos --redirect -n \
            && ok "Certificado Let's Encrypt emitido e Nginx configurado com HTTPS automaticamente." \
            || warn "Falha ao emitir o certificado Let's Encrypt. O site continua funcionando em HTTP; rode 'sudo certbot --nginx -d $DOMINIO' depois de corrigir o DNS."
        # O pacote certbot já instala o timer systemd de renovação automática
        # (certbot.timer) — nada a fazer aqui.
        ;;
    zerossl)
        log "Instalando acme.sh e emitindo certificado ZeroSSL para $DOMINIO..."
        if [ ! -x "/root/.acme.sh/acme.sh" ]; then
            curl -s https://get.acme.sh | sh -s email="$EMAIL_SSL"
        fi
        ACME="/root/.acme.sh/acme.sh"
        "$ACME" --set-default-ca --server zerossl
        "$ACME" --register-account -m "$EMAIL_SSL" --server zerossl || true
        mkdir -p "$CERT_DIR"
        if "$ACME" --issue -d "$DOMINIO" -w "$WEBROOT_ACME" --server zerossl; then
            "$ACME" --install-cert -d "$DOMINIO" \
                --key-file       "$CERT_DIR/privkey.pem" \
                --fullchain-file "$CERT_DIR/fullchain.pem" \
                --reloadcmd      "systemctl reload nginx"

            # Reescreve o site do Nginx com o bloco HTTPS + redirecionamento
            cat > "$NGINX_SITE" <<EOF
upstream ${SERVICE_NAME}_app {
    server 127.0.0.1:$PORT;
}

server {
    listen 80;
    listen [::]:80;
    server_name $DOMINIO;

    location /.well-known/acme-challenge/ {
        root $WEBROOT_ACME;
    }

    location / {
        return 301 https://\$host\$request_uri;
    }
}

server {
    listen 443 ssl http2;
    listen [::]:443 ssl http2;
    server_name $DOMINIO;

    ssl_certificate     $CERT_DIR/fullchain.pem;
    ssl_certificate_key $CERT_DIR/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers HIGH:!aNULL:!MD5;

    client_max_body_size 26M;

    location /static/ {
        alias $APP_DIR/app/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location / {
        proxy_pass http://${SERVICE_NAME}_app;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_redirect off;
        proxy_read_timeout 60s;
    }
}
EOF
            nginx -t && systemctl reload nginx
            ok "Certificado ZeroSSL emitido e Nginx configurado com HTTPS."
            echo "  (acme.sh já instalou sua própria rotina de renovação automática via cron.)"
        else
            warn "Falha ao emitir o certificado ZeroSSL. O site continua em HTTP; verifique o DNS e rode este script de novo."
        fi
        ;;
    *)
        warn "Instalação sem SSL — o acesso é HTTP simples."
        ;;
esac

# ---------------------------------------------------------------------------
# 9) Firewall
# ---------------------------------------------------------------------------
log "Passo 8/8 — Configurando o firewall (ufw)..."
ufw allow OpenSSH >/dev/null 2>&1 || true
ufw allow 'Nginx Full' >/dev/null 2>&1 || ufw allow 80/tcp && ufw allow 443/tcp
ufw --force enable >/dev/null 2>&1 || true
ok "Firewall configurado (SSH, 80 e 443 liberados; mais nada exposto)."

# ---------------------------------------------------------------------------
# Resumo final
# ---------------------------------------------------------------------------
if [ "$MODO_ACESSO" = "dominio" ] && [ "$SSL_PROVIDER" != "nenhum" ]; then
    URL="https://$DOMINIO"
elif [ "$MODO_ACESSO" = "dominio" ]; then
    URL="http://$DOMINIO"
else
    URL="http://${SERVER_IP}"
fi

echo ""
echo -e "${C_GREEN}${C_BOLD}============================================================${C_RESET}"
echo -e "${C_GREEN}${C_BOLD} Deploy concluído!${C_RESET}"
echo -e "${C_GREEN}${C_BOLD}============================================================${C_RESET}"
echo ""
echo "  Acesse: $URL"
echo "  Usuário admin: $ADMIN_USERNAME"
if [ "${ADMIN_PASSWORD_GERADA:-0}" = "1" ]; then
    echo "  Senha admin (gerada automaticamente, guarde em local seguro): $ADMIN_PASSWORD"
else
    echo "  Senha admin: a que você digitou."
fi
echo ""
echo "  Serviço:  systemctl status $SERVICE_NAME"
echo "  Logs:     journalctl -u $SERVICE_NAME -f"
echo "  Nginx:    /etc/nginx/sites-available/${SERVICE_NAME}.conf"
echo "  Config:   $CONF_FILE (usada pelo update.sh — não apague)"
echo ""
echo "  Para atualizar o SCA no futuro, use: sudo ./update.sh"
echo ""
