# SCA — Sistema de Cidades e Avisos (Backend)

Backend Flask completo para o front-end (Alpine.js), com persistência
real, autenticação, API REST, cache, rate limiting, headers de segurança
e infraestrutura pronta para produção (Gunicorn + Nginx).

**Roda em SQLite por padrão — zero configuração.** PostgreSQL é opcional,
para quando você quiser subir em produção com mais concorrência.

## Stack

| Camada | Tecnologia |
|---|---|
| Framework | Flask |
| Banco de dados | SQLite (padrão) ou PostgreSQL, via SQLAlchemy (ORM) |
| Migrações | Alembic (via Flask-Migrate) |
| Autenticação | Flask-Login (sessão de servidor) |
| Formulários / CSRF | Flask-WTF |
| Rate limiting | Flask-Limiter |
| Headers de segurança | Flask-Talisman |
| Cache | Flask-Caching |
| Sessão | Flask-Session |
| Validação de entrada | Pydantic |
| Serialização de saída | Marshmallow |
| Upload/otimização de imagens | Pillow |
| Config | python-dotenv |
| Servidor de produção | Gunicorn |
| Proxy reverso | Nginx (opcional) |

## Início rápido (1 comando)

```bash
cd sca_backend
./setup.sh
```

Isso cria o ambiente virtual, instala as dependências, aplica as
migrations num banco SQLite local (`app.db`), popula dados de exemplo e
sobe o servidor em `http://localhost:5000`.

Login padrão criado pelo seed: **admin / admin123** (administrador) e
**usuario / usuario123** (usuário comum já aprovado, útil para testar a
área pública/chat) — troque as senhas com `flask create-admin` antes de
usar de verdade.

Não precisa de PostgreSQL, Redis, nem arquivo `.env` para isso funcionar.

## Estrutura do projeto

```
sca_backend/
├── app/
│   ├── __init__.py          # app factory (extensões, blueprints, error handlers)
│   ├── extensions.py         # instâncias das extensões Flask
│   ├── models.py             # User, Cidade, Aviso (SQLAlchemy)
│   ├── schemas.py            # validação (Pydantic) e serialização (Marshmallow)
│   ├── forms.py              # Flask-WTF (CSRF)
│   ├── auth/                  # login, logout, sessão (blueprint /api/auth)
│   ├── api/                   # CRUD de cidades, avisos, upload de imagem (/api)
│   ├── main/                   # rota que serve o front-end (/)
│   ├── templates/
│   │   ├── index.html          # shell da página, só monta as partials
│   │   └── partials/            # cada seção da UI em seu próprio arquivo
│   │       ├── _login.html
│   │       ├── _nav.html
│   │       ├── _admin.html
│   │       ├── _public.html
│   │       ├── _modal_cidade.html
│   │       ├── _modal_aviso.html
│   │       ├── _toast.html
│   │       └── _confirm_modal.html
│   └── static/
│       ├── css/app.css          # estilos (antes inline no HTML)
│       ├── js/app.js            # lógica Alpine.js + chamadas fetch() à API
│       └── uploads/              # imagens enviadas (Pillow)
├── migrations/                  # Alembic (já inicializado, com a migration inicial)
├── config.py                    # config única, 100% por variável de ambiente
├── wsgi.py                      # entry point (dev e produção)
├── gunicorn.conf.py
├── nginx.conf                    # exemplo, uso opcional
├── Procfile                       # deploy em 1 clique (Render/Railway/Heroku-like)
├── setup.sh                       # sobe tudo em desenvolvimento com 1 comando
├── seed.py                        # dados de exemplo (iguais aos do front original)
├── requirements.txt
└── .env.example
```

O HTML deixou de ser um arquivo único de ~1700 linhas: agora cada seção
da interface (login, navbar, painel admin, área pública, os dois modais,
toast, confirmação) vive em seu próprio arquivo dentro de
`app/templates/partials/`, incluído no `index.html` via
`{% include %}`. CSS e JavaScript também saíram do HTML e viraram
arquivos próprios em `app/static/`.

## Modelo de dados

- **User**: `username`, `password_hash`, `role` (admin/usuario), `status`
  (pendente/aprovado/reprovado). Visitantes se cadastram sozinhos e ficam
  `pendente` até o admin aprovar.
- **Cidade**: `nome`, `perfil` (matriz/filial), `imagemUrl` (otimizada
  automaticamente no upload), `modoPrazo` (periodo/dataHora/semData),
  `prazoInicio`, `prazoFim`, `regraHoras` ("Prazo de O.S" na interface),
  `observacao` (usada como aviso/legenda breve no card), `tecnicosFimSemana`,
  `tipoAberturaFimSemana`, `plantonistaFDS`, `modoAutoPlantonista`.
- **Aviso**: `titulo`, `descricao`, `modoDuracao` (dias/horas), `inicio`,
  `fim`, `duracaoHoras`. O `status` (Aguardando/Ativo/Expirado) é calculado
  dinamicamente a cada resposta da API.
- **ChatMessage**: `conteudo`, `autor` (User), `criadoEm`, `editadoEm`.

Os nomes de campo trafegados pela API são os mesmos usados pelo
Alpine.js (`camelCase`), então o front-end não precisa de nenhuma
tradução extra.

## Funcionalidades da área pública

- **Acesso restrito por aprovação**: visitantes se cadastram (usuário +
  senha) e ficam com status `pendente` até o administrador aprovar em
  Painel Admin → Usuários. Só depois disso conseguem ver cidades, avisos
  e o chat interno.
- **Cards de cidade**: imagem (enviada pelo admin e redimensionada/otimizada
  automaticamente com Pillow), nome, breve aviso/observação e uma barra de
  progresso rotulada **"Cidade com Limitação de O.S"** quando há prazo
  operacional ativo. Clique no card para ver todos os detalhes (prazo
  completo, "Prazo de O.S", plantonista de fim de semana, tipo de abertura).
- **Clima atual**: carregado automaticamente por cidade via Open-Meteo
  (gratuito, sem chave de API), com cache de ~30 min por cidade. Se a API
  externa estiver indisponível, o card simplesmente não mostra o badge de
  clima — não quebra a página.
- **Carrossel de avisos**: os avisos vigentes/agendados aparecem em um
  carrossel animado no topo da página pública, trocando automaticamente a
  cada 6 segundos.
- **Chat interno**: usuários aprovados podem conversar, mandar links
  (detectados e transformados em `<a>` automaticamente) e editar/apagar
  apenas as próprias mensagens. O administrador pode apagar mensagens de
  qualquer pessoa. Atualiza via polling a cada 4s enquanto a aba está aberta.

## Rotas da API

```
GET    /api/cidades                 (usuário aprovado ou admin)
GET    /api/cidades/<id>            (usuário aprovado ou admin)
GET    /api/cidades/<id>/clima      (usuário aprovado ou admin — clima atual)
POST   /api/cidades                 (admin)
PUT    /api/cidades/<id>             (admin)
DELETE /api/cidades/<id>             (admin)
GET    /api/cidades/estatisticas    (admin)

GET    /api/avisos                  (usuário aprovado ou admin)
GET    /api/avisos/<id>             (usuário aprovado ou admin)
POST   /api/avisos                  (admin)
PUT    /api/avisos/<id>              (admin)
DELETE /api/avisos/<id>              (admin)
GET    /api/avisos/estatisticas     (admin)

POST   /api/uploads/imagem          (admin — Pillow redimensiona/otimiza)

GET    /api/chat/mensagens          (usuário aprovado ou admin; ?com=<id> = DM, ?grupo=<id> = grupo)
POST   /api/chat/mensagens          (usuário aprovado ou admin; body aceita destinatarioId OU grupoId)
PUT    /api/chat/mensagens/<id>      (autor da mensagem)
DELETE /api/chat/mensagens/<id>      (autor da mensagem; admin só no chat geral)
GET    /api/chat/usuarios            (diretório leve p/ iniciar conversa privada)
GET    /api/chat/grupos              (grupos dos quais participo; admin vê todos)
POST   /api/chat/grupos              (cria um grupo — vira admin dele automaticamente)
PUT    /api/chat/grupos/<id>          (admin do grupo ou do sistema)
DELETE /api/chat/grupos/<id>          (admin do grupo ou do sistema)
GET    /api/chat/grupos/<id>/membros
POST   /api/chat/grupos/<id>/membros           (admin do grupo — body: {membrosIds: [...]})
DELETE /api/chat/grupos/<id>/membros/<user_id>  (sair = próprio ID; remover outro = admin do grupo)

GET    /api/admin/usuarios                    (admin — lista/filtra por status)
POST   /api/admin/usuarios/<id>/aprovar        (admin)
POST   /api/admin/usuarios/<id>/reprovar       (admin)
PUT    /api/admin/usuarios/<id>                 (admin — troca usuário/senha)
DELETE /api/admin/usuarios/<id>                 (admin)

GET    /api/auth/csrf-token
POST   /api/auth/registrar          (público — cria conta 'pendente'; rate limit: 5/hora)
POST   /api/auth/login              (rate limit: 10/min)
POST   /api/auth/logout
GET    /api/auth/me
GET    /api/auth/sessoes                     (lista as sessões/dispositivos ativos do usuário logado)
POST   /api/auth/sessoes/encerrar-outras     (derruba todas as sessões, exceto a atual)
DELETE /api/auth/sessoes/<id>                 (encerra uma sessão específica)
```

Rotas de escrita exigem sessão autenticada (Flask-Login) **e** o header
`X-CSRFToken` (obtido em `/api/auth/csrf-token`) — o `app.js` já faz isso
automaticamente.

> A integração de clima usa `api.open-meteo.com` e
> `geocoding-api.open-meteo.com` — nenhuma chave é necessária, mas o
> servidor onde a aplicação rodar precisa ter saída de internet liberada
> para esses domínios. Se não tiver, o recurso degrada graciosamente (o
> card simplesmente não mostra o clima).

## Rodando manualmente (sem o setup.sh)

```bash
cd sca_backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

export FLASK_APP=wsgi.py
flask db upgrade          # cria o app.db (SQLite) e aplica as migrations
flask seed-db              # popula com os dados de exemplo
flask create-admin         # cria/troca seu usuário administrador

flask run
```

Acesse `http://localhost:5000`. Nenhum `.env` é necessário para isso.

## Usando PostgreSQL em vez de SQLite

```bash
sudo -u postgres psql -c "CREATE DATABASE sca_db;"
sudo -u postgres psql -c "CREATE USER sca_user WITH PASSWORD 'sca_pass';"
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE sca_db TO sca_user;"
```

Copie `.env.example` para `.env` e descomente/ajuste:
```
DATABASE_URL=postgresql+psycopg2://sca_user:sca_pass@localhost:5432/sca_db
```

Depois: `flask db upgrade`.

## Migrações (Alembic / Flask-Migrate)

O diretório `migrations/` já contém a migration inicial. Para alterações
futuras de modelo:

```bash
flask db migrate -m "descrição da mudança"
flask db upgrade
```

Reverter a última migration: `flask db downgrade`.

## Deploy

### Opção A — mais simples: PaaS com Procfile (Render, Railway, etc.)

O `Procfile` já está pronto:
```
web: gunicorn -c gunicorn.conf.py wsgi:app
release: flask db upgrade
```

Basta conectar o repositório na plataforma, definir `SECRET_KEY` (e
`DATABASE_URL` se for usar Postgres gerenciado) nas variáveis de
ambiente, e o deploy sobe sozinho — sem precisar configurar Nginx nem
systemd manualmente. Com SQLite, monte um volume persistente para o
arquivo `app.db` (ou use o Postgres gerenciado da plataforma).

Praticamente toda plataforma PaaS coloca a aplicação atrás de um proxy —
defina também `TRUST_PROXY_HEADERS=true` (ver `.env.example`).

> ⚠️ **Importante**: se a plataforma oferecer cache de borda / CDN para a
> aplicação (não para assets estáticos, e sim para as respostas da própria
> aplicação), **mantenha essa opção desligada** para este projeto. A
> aplicação já envia `Cache-Control: no-store` em toda resposta dinâmica
> justamente para impedir isso, mas alguns provedores têm modos
> "cache tudo" que ignoram esse header — não ative esse tipo de
> configuração aqui, ou sessões de usuários diferentes podem se misturar.

### Opção B — servidor próprio (Gunicorn + Nginx)

```bash
pip install -r requirements.txt
cp .env.example .env   # preencha com valores reais de produção, incluindo TRUST_PROXY_HEADERS=true

./entrypoint.sh
```

`entrypoint.sh` substitui o `flask db upgrade` + `gunicorn` manuais: ele
espera o Postgres aceitar conexões (útil quando o banco sobe em outro
container/host e ainda não está pronto), aplica as migrations, cria o
primeiro admin automaticamente se `ADMIN_USERNAME`/`ADMIN_PASSWORD`
estiverem no `.env`, e só então inicia o Gunicorn. É seguro rodar em todo
deploy/restart — se já estiver tudo migrado, ele não faz nada de novo.

Se preferir os passos manuais (ou não usa Postgres):
```bash
flask db upgrade
flask create-admin      # cria o admin interativamente
gunicorn -c gunicorn.conf.py wsgi:app
```

> **Sobre o Postgres:** as migrations já foram corrigidas para criar
> explicitamente os tipos `ENUM` no Postgres antes de usá-los (isso é
> necessário lá, mas não em SQLite/dev, onde enum vira só texto — por isso
> o problema só aparecia "na hora de ir pra produção"). Rodar
> `flask db upgrade` mais de uma vez (ex.: a cada deploy) é seguro.

Configure o Nginx com o `nginx.conf` incluso (ajuste `server_name` e os
caminhos do certificado SSL) apontando para `127.0.0.1:8000`. **Não
adicione `proxy_cache` para esta aplicação** — ela já controla seu próprio
cache via `Cache-Control`, e um cache de proxy que ignore esse header
reintroduziria o mesmo risco de vazamento de sessão entre usuários.

Exemplo de unit systemd:

```ini
# /etc/systemd/system/sca.service
[Unit]
Description=SCA Backend (Gunicorn)
After=network.target postgresql.service

[Service]
User=www-data
WorkingDirectory=/var/www/sca_backend
EnvironmentFile=/var/www/sca_backend/.env
ExecStart=/var/www/sca_backend/.venv/bin/bash entrypoint.sh
Restart=always

[Install]
WantedBy=multi-user.target
```

> Com SQLite, mantenha `GUNICORN_WORKERS=1` ou `2` (padrão do
> `gunicorn.conf.py`) — é o suficiente para tráfego pequeno/médio e evita
> problemas de concorrência de escrita do SQLite. Para mais workers/mais
> tráfego, migre para PostgreSQL e defina `REDIS_URL` no `.env` para
> compartilhar sessão/cache/rate-limit entre os processos.

## Concorrência e robustez sob múltiplos usuários simultâneos

- **XSS armazenado corrigido no chat** (`linkify()` em app.js): mensagens
  eram escapadas contra `<`/`>`/`&`, mas não contra aspas. Uma mensagem
  como `https://x.com" onmouseover="alert(1)` escapava do atributo
  `href` do link gerado e injetava um atributo/evento arbitrário no HTML
  — um XSS de verdade, disparado só de alguém ler o chat. Corrigido
  escapando aspas simples e duplas antes de detectar links.
- **Gráficos do painel administrativo** (`renderizarOuAtualizarGraficos`):
  corrigido o erro `Cannot set properties of undefined (setting
  'fullSize')` — o Chart.js corrompe o estado interno de um gráfico
  quando `.update()` é chamado num canvas invisível/com tamanho zero, ou
  quando duas atualizações se sobrepõem no tempo (ex.: excluir um aviso
  dispara isso quase ao mesmo tempo que a sincronização automática). Agora
  a função sempre destrói e recria o gráfico do zero (em vez de reusar
  uma instância que pode estar presa a um canvas antigo), ignora canvases
  que não estão de fato visíveis, tem uma trava contra chamadas
  sobrepostas, e nunca deixa uma falha de gráfico interromper a ação que
  a disparou.
- **Carrossel de avisos**: os slides não eram posicionados com
  `absolute`, então durante a transição (que sobrepõe a saída de um slide
  com a entrada do próximo) os dois ficavam empilhados no fluxo normal do
  documento — daí o "aparece embaixo e buga". Corrigido posicionando cada
  slide de forma absoluta dentro de um contêiner com altura mínima fixa.

Testado com carga concorrente real (não só lida no código) usando um
worker pool de 15 threads disparando requisições ao mesmo tempo contra um
servidor Gunicorn de verdade, em SQLite e em Postgres:

- **Criação com nome duplicado** (15 requisições simultâneas tentando
  criar o mesmo usuário): exatamente 1 é criada, as outras 14 recebem um
  erro 409 limpo — nunca duas contas com o mesmo usuário.
- **Exclusão duplicada** (10 requisições simultâneas apagando o mesmo
  aviso/cidade/usuário/mensagem): exatamente 1 sucesso, as demais um 404
  limpo. Isso corrigiu um bug real encontrado durante o teste: o SQLite
  não reporta de forma confiável quando uma linha já foi apagada por outra
  transação (`StaleDataError` da ORM não dispara), o que fazia exclusões
  concorrentes retornarem "sucesso" falso sem apagar nada de fato. Todas
  as rotas de exclusão (avisos, cidades, usuários, mensagens de chat)
  agora conferem a quantidade real de linhas afetadas antes de responder.
- **Edições concorrentes no mesmo registro**: não derrubam o servidor;
  a última escrita prevalece (sem trava otimista — para o volume desta
  aplicação, isso é aceitável e mais simples do que versionamento).
- **Papel de administrador**: promover/rebaixar usa `SELECT ... FOR
  UPDATE` para evitar que duas operações simultâneas deixem o sistema sem
  nenhum admin (efetivo em Postgres; SQLite serializa escritas de qualquer
  forma).
- **Gunicorn com `worker_class = gthread`**: antes, o `threads` configurado
  não tinha efeito nenhum (o worker padrão do Gunicorn, `sync`, ignora essa
  opção silenciosamente) — cada worker atendia uma requisição de cada vez.
  Agora múltiplas requisições são atendidas de verdade em paralelo por
  worker.
- **SQLite em modo WAL + `busy_timeout`**: reduz drasticamente os erros
  "database is locked" sob acesso concorrente (leituras não ficam mais
  bloqueadas por uma escrita em andamento; uma escrita concorrente espera
  alguns segundos em vez de falhar na hora). Não tem efeito em Postgres.
- **Trava contra duplo-clique/duplo-envio** no front-end: os formulários de
  cidade, aviso, perfil, senha, personalização, novo usuário e envio de
  chat ignoram um segundo envio enquanto o primeiro ainda está em
  andamento, e o botão mostra "Salvando..." nesse meio tempo.
- **Sessão de banco sempre revertida em caso de erro** (`teardown_
  appcontext`): uma exceção não tratada em uma requisição não deixa a
  conexão do pool "envenenada" para a próxima requisição que reutilizá-la.
- Isolamento de sessão entre usuários — ver a seção anterior — já cobre a
  parte de "um usuário nunca vê/age com a sessão de outro".

## Segurança já incluída

- **Isolamento de sessão entre usuários/navegadores — o ponto mais crítico**:
  **nenhuma resposta dinâmica** (a página principal `/`, e tudo em `/api/*`)
  pode ser guardada em cache por navegador, proxy reverso ou CDN. Toda
  resposta que não seja um arquivo estático leva
  `Cache-Control: no-store, no-cache, must-revalidate, private` +
  `Pragma: no-cache` + `Vary: Cookie`.
  Por quê isso importa: o Flask reemite o cookie de sessão (`Set-Cookie`)
  em praticamente toda resposta autenticada — inclusive na própria página
  principal, que é a URL compartilhada entre pessoas. Se alguma camada de
  cache no caminho (CDN, proxy da hospedagem, etc.) guardasse essa resposta
  específica com o `Set-Cookie` de quem a gerou, qualquer pessoa que
  abrisse o mesmo link depois receberia o cookie de sessão da primeira —
  aparecendo "logada" como ela, mesmo sem ter digitado usuário/senha. É
  exatamente esse comportamento que os headers acima eliminam. Combinado a
  isso, nenhuma rota autenticada usa `@cache.cached()` (que teria o mesmo
  problema, só que no nível da aplicação em vez de um proxy externo).
- **Segunda camada de validação de sessão, independente do cookie**
  (`app/auth/guard.py` + tabela `sessoes_usuario`): cada login bem-sucedido
  cria um registro próprio (token aleatório, dispositivo, IP, últimos
  acessos). Toda requisição autenticada é conferida contra esse registro —
  não só contra o que o cookie/Flask-Login afirmam. Qualquer divergência
  (sessão revogada em outro lugar, ou qualquer coisa que fizesse dois
  cookies apontarem pro mesmo dado por engano) derruba a sessão na hora.
  Isso também é o que sustenta:
  - **Múltiplas sessões simultâneas sem vazamento**: o mesmo usuário pode
    estar logado em vários dispositivos ao mesmo tempo, cada um isolado;
    `GET /api/auth/sessoes` lista os dispositivos ativos, e
    `DELETE /api/auth/sessoes/<id>` ou
    `POST /api/auth/sessoes/encerrar-outras` encerram sessões individuais
    remotamente (ex.: "esqueci de sair no computador da empresa").
  - **Rotação do ID de sessão no login** (proteção contra fixação de
    sessão): o identificador interno da sessão é substituído por um novo a
    cada login bem-sucedido, não só o conteúdo.
  - **Revogação instantânea pelo admin**: reprovar um usuário ou trocar a
    senha de alguém (`PUT /api/admin/usuarios/<id>`) já derruba, na
    próxima requisição, qualquer sessão que essa pessoa tivesse aberta —
    sem esperar a sessão expirar sozinha.
- **IP real do visitante atrás de proxy/CDN** (`TRUST_PROXY_HEADERS`): em
  produção, praticamente todo deploy fica atrás de algum proxy reverso.
  Sem informar isso ao Flask, todas as requisições parecem vir do IP do
  proxy — o que enfraquece a proteção "strong" de sessão do Flask-Login
  (que usa IP + navegador para perceber quando uma sessão está sendo usada
  de um lugar diferente do original) e o rate limiting por IP do
  Flask-Limiter. Ative `TRUST_PROXY_HEADERS=true` no `.env` quando estiver
  atrás de um proxy confiável (ver `.env.example`).
- **Login case-insensitive e sem contas duplicadas por capitalização**:
  nomes de usuário são normalizados para minúsculas no cadastro e
  comparados sem diferenciar maiúsculas/minúsculas no login.
- **Cadastros pendentes/reprovados nunca recebem sessão autenticada**: o
  backend só cria uma sessão de login para administradores ou usuários já
  aprovados — reduz a superfície de ataque, já que não existe cookie de
  sessão válido para uma conta ainda não aprovada.
- **Mensagens de erro genéricas no login** (não revelam se o usuário
  existe), e o token CSRF é renovado a cada login/logout.
- **Sessão assinada** (`SESSION_USE_SIGNER`) e cookies de sessão/"lembrar-me"
  com `HttpOnly`, `SameSite=Lax` e `Secure` (em produção com HTTPS).
- **Flask-Talisman**: HSTS, CSP, `X-Content-Type-Options`,
  `X-Frame-Options`, cookies `Secure` em produção.
- **Flask-Limiter**: limite geral de requisições + limite mais restritivo
  no login e no cadastro (proteção contra força bruta e spam de contas).
- **Flask-WTF (CSRF)**: obrigatório em toda rota de escrita.
- **Senhas**: hash com `werkzeug.security` (PBKDF2).
- **Validação Pydantic**: toda entrada da API é validada antes de tocar
  no banco.
- **Upload de imagem**: valida o conteúdo real do arquivo com Pillow,
  redimensiona e reencoda.

## Comandos úteis

```bash
flask create-admin     # cria/verifica um usuário administrador
flask seed-db          # popula cidades/avisos de exemplo (idempotente)
flask db migrate -m "" # gera nova migration a partir dos models
flask db upgrade       # aplica migrations pendentes
```
