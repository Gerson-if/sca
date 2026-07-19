import secrets
from datetime import datetime, timezone

from flask import current_app, jsonify, request, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_wtf.csrf import generate_csrf
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.auth import auth_bp
from app.extensions import db, limiter
from app.models import User, StatusUsuario, SessaoUsuario, TemaPreferencia
from app.schemas import LoginIn, RegistroIn, PerfilIn, TemaIn


def _ip_do_cliente() -> str:
    # Sem TRUST_PROXY_HEADERS + ProxyFix (ver app/__init__.py), o Flask só
    # enxerga o IP do proxy; aqui é só para fins informativos (exibição em
    # "sessões ativas"), então usamos o mesmo request.remote_addr que o
    # restante do app já usa para rate limiting.
    return request.remote_addr or ""


def _criar_sessao_usuario(user: User) -> str:
    """Cria o registro de sessão (2ª camada de validação, independente do
    cookie) e devolve o token que deve ser guardado em `session`."""
    token = secrets.token_urlsafe(32)
    sessao = SessaoUsuario(
        user_id=user.id,
        token=token,
        user_agent=(request.headers.get("User-Agent") or "")[:255],
        ip_address=_ip_do_cliente(),
    )
    db.session.add(sessao)
    db.session.commit()
    return token


@auth_bp.get("/csrf-token")
def csrf_token():
    """O Flask-WTF injeta o token de CSRF na sessão; expomos aqui para que o
    front-end (SPA/Alpine) consiga enviá-lo de volta no header X-CSRFToken."""
    return jsonify({"csrfToken": generate_csrf()})


@auth_bp.post("/registrar")
@limiter.limit("5 per hour")  # evita spam de cadastros
def registrar():
    """Cadastro público. A conta nasce 'pendente' e só pode logar de fato
    depois que o administrador aprovar (ver /api/admin/usuarios)."""
    payload = request.get_json(silent=True) or {}
    try:
        data = RegistroIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    # Comparação sempre normalizada (minúsculas) para não permitir contas
    # "duplicadas" que só diferem por maiúsculas/minúsculas.
    existente = User.query.filter(db.func.lower(User.username) == data.username).first()
    if existente:
        return jsonify({"error": "Esse nome de usuário já está em uso."}), 409

    user = User(username=data.username, status=StatusUsuario.pendente)
    user.set_password(data.password)
    db.session.add(user)
    try:
        db.session.commit()
    except IntegrityError:
        # Duas pessoas podem enviar o mesmo username ao mesmo tempo — a
        # verificação acima sozinha não fecha essa brecha (é
        # "checar-depois-agir", com uma janela entre as duas). A
        # constraint UNIQUE do banco é quem garante de verdade; aqui só
        # traduzimos a falha dela numa mensagem amigável em vez de um 500.
        db.session.rollback()
        return jsonify({"error": "Esse nome de usuário já está em uso."}), 409

    return jsonify({
        "message": "Cadastro enviado! Assim que o administrador aprovar, você poderá acessar normalmente."
    }), 201


@auth_bp.post("/login")
@limiter.limit("10 per minute")  # protege contra força bruta
def login():
    payload = request.get_json(silent=True) or {}
    try:
        data = LoginIn(**payload)
    except ValidationError as exc:
        primeira_msg = exc.errors()[0]["msg"].replace("Value error, ", "")
        return jsonify({"error": primeira_msg}), 400

    username_normalizado = data.username.strip().lower()
    user = User.query.filter(db.func.lower(User.username) == username_normalizado).first()

    # Mensagem sempre genérica quando as credenciais não conferem — não
    # revela se o usuário existe ou não (evita enumeração de contas).
    if user is None or not user.check_password(data.password) or not user.is_active:
        return jsonify({"error": "Usuário ou senha inválidos."}), 401

    # Cadastros pendentes/reprovados NUNCA recebem uma sessão autenticada.
    # Isso reduz a superfície de ataque: só existe cookie de sessão válido
    # para quem é admin ou já foi aprovado.
    if not user.is_admin:
        if user.status == StatusUsuario.reprovado:
            return jsonify({
                "error": "Seu cadastro não foi aprovado pelo administrador.",
                "status": "reprovado",
            }), 403
        if user.status == StatusUsuario.pendente:
            return jsonify({
                "error": "Seu cadastro ainda está em análise. Aguarde a aprovação do administrador.",
                "status": "pendente",
                "username": user.username,
            }), 403

    # Mitiga fixação de sessão: descarta qualquer sessão anterior (por
    # exemplo, uma sessão anônima já existente neste navegador) antes de
    # autenticar, forçando o Flask-Session a emitir um identificador novo.
    session.clear()

    # REMOVIDO o "manter conectado" (sessão persistente / remember_token).
    # Esse recurso emitia um cookie "remember_token" com validade de dias,
    # suficiente para o Flask-Login reautenticar sozinho a PRÓXIMA pessoa
    # que abrisse aquele navegador — ou que recebesse o link do projeto já
    # com aquele cookie no navegador — sem digitar usuário/senha nenhum.
    # Era exatamente a causa do "compartilhei o link e a pessoa caiu na
    # minha sessão". Agora TODO login usa `remember=False` e
    # `session.permanent = False`, incondicionalmente: nenhum remember_token
    # é emitido, e o cookie de sessão dura apenas enquanto o navegador
    # continuar aberto. Fechou o navegador (ou usou outro navegador/
    # dispositivo/link), a sessão anterior não existe mais e é obrigatório
    # logar de novo com usuário e senha corretos.
    #
    # Quem quiser não digitar a senha de novo pode usar o recurso nativo do
    # PRÓPRIO navegador para lembrar usuário/senha (por isso os campos do
    # formulário de login têm autocomplete="username"/"current-password") —
    # isso é responsabilidade do navegador, não do sistema, e não cria um
    # cookie de sessão de longa duração que possa vazar por um link.
    login_user(user, remember=False)
    session.permanent = False

    # Rotaciona o identificador de sessão do lado do servidor (não só o
    # conteúdo, que já foi limpo acima com session.clear()). Sem isso, um
    # id de sessão conhecido/fixado ANTES do login continuaria válido
    # DEPOIS do login (fixação de sessão): quem soubesse esse id de sessão
    # anônimo poderia usá-lo para "herdar" o login de outra pessoa. O
    # Flask-Session (>=0.6) expõe `regenerate()` no session_interface
    # exatamente para isso; se o backend em uso não suportar (ex.: sessão
    # padrão do Flask em testes), ignoramos silenciosamente.
    regenerate = getattr(current_app.session_interface, "regenerate", None)
    if callable(regenerate):
        regenerate(session)

    # Segunda camada de validação, independente do cookie (ver
    # app/auth/guard.py e SessaoUsuario em app/models.py): cada login gera
    # um registro próprio, e todo request autenticado é conferido contra
    # ele. Isso também é a base para "múltiplas sessões simultâneas sem
    # vazamento" — cada dispositivo/navegador tem o seu, e podem ser
    # listados/encerrados individualmente em /api/auth/sessoes.
    session["session_token"] = _criar_sessao_usuario(user)

    return jsonify({
        "message": "Login realizado com sucesso.",
        "user": user.to_dict(),
        # Como a sessão foi recriada acima, o token de CSRF antigo (obtido
        # antes do login) deixa de ser válido; devolvemos um novo já aqui
        # para o front-end não precisar de uma segunda chamada.
        "csrfToken": generate_csrf(),
    })


@auth_bp.post("/logout")
@login_required
def logout():
    token = session.get("session_token")
    if token:
        SessaoUsuario.query.filter_by(token=token).update(
            {"revoked_at": datetime.now(timezone.utc)}
        )
        db.session.commit()
    logout_user()
    session.clear()
    return jsonify({"message": "Sessão encerrada.", "csrfToken": generate_csrf()})


@auth_bp.get("/me")
def me():
    if current_user.is_authenticated:
        return jsonify({"loggedIn": True, "user": current_user.to_dict()})
    return jsonify({"loggedIn": False, "user": None})


@auth_bp.get("/sessoes")
@login_required
def listar_sessoes():
    """Lista as sessões (dispositivos/navegadores) ativas do usuário logado,
    marcando qual delas é a sessão atual."""
    token_atual = session.get("session_token")
    sessoes = (
        SessaoUsuario.query.filter_by(user_id=current_user.id, revoked_at=None)
        .order_by(SessaoUsuario.last_seen_at.desc())
        .all()
    )
    return jsonify({
        "sessoes": [s.to_dict(atual=(s.token == token_atual)) for s in sessoes]
    })


@auth_bp.post("/sessoes/encerrar-outras")
@login_required
def encerrar_outras_sessoes():
    """Derruba todas as sessões do usuário logado, exceto a atual — útil
    para "sair de todos os outros dispositivos" após suspeita de acesso
    indevido."""
    token_atual = session.get("session_token")
    (
        SessaoUsuario.query.filter(
            SessaoUsuario.user_id == current_user.id,
            SessaoUsuario.token != token_atual,
            SessaoUsuario.revoked_at.is_(None),
        ).update({"revoked_at": datetime.now(timezone.utc)}, synchronize_session=False)
    )
    db.session.commit()
    return jsonify({"message": "As demais sessões foram encerradas."})


@auth_bp.delete("/sessoes/<int:sessao_id>")
@login_required
def encerrar_sessao(sessao_id):
    """Encerra uma sessão específica do próprio usuário (ex.: um
    dispositivo perdido/roubado)."""
    sessao = SessaoUsuario.query.filter_by(id=sessao_id, user_id=current_user.id).first()
    if sessao is None:
        return jsonify({"error": "Sessão não encontrada."}), 404
    sessao.revoked_at = datetime.now(timezone.utc)
    db.session.commit()
    # Se a pessoa encerrou a PRÓPRIA sessão atual, também precisamos
    # derrubar o cookie local imediatamente (senão o guard só pegaria isso
    # na próxima requisição, mas o cookie ainda pareceria "autenticado").
    if sessao.token == session.get("session_token"):
        logout_user()
        session.clear()
    return jsonify({"message": "Sessão encerrada."})


# ------------------------------------------------------------------
# PERFIL DO PRÓPRIO USUÁRIO (nome, senha, foto, tema)
# ------------------------------------------------------------------
@auth_bp.put("/perfil")
@login_required
@limiter.limit("20 per minute")
def atualizar_perfil():
    """Permite à pessoa logada mudar seu nome de exibição e, opcionalmente,
    trocar a própria senha (exige a senha atual — evita que alguém que
    "pegue" uma sessão aberta troque a senha e tranque o dono de fora)."""
    payload = request.get_json(silent=True) or {}
    try:
        data = PerfilIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    if data.novaSenha:
        if not current_user.check_password(data.senhaAtual):
            return jsonify({"error": "Senha atual incorreta."}), 400
        current_user.set_password(data.novaSenha)

    current_user.nome = data.nome
    db.session.commit()
    return jsonify(current_user.to_dict())


@auth_bp.post("/perfil/foto")
@login_required
@limiter.limit("10 per minute")
def atualizar_foto_perfil():
    """Upload da própria foto de perfil (qualquer usuário logado — não
    exige ser admin, ao contrário do upload genérico de mídia)."""
    from app.api.uploads import processar_e_salvar_imagem

    if "arquivo" not in request.files:
        return jsonify({"error": "Nenhum arquivo enviado (campo 'arquivo')."}), 400

    try:
        # Fotos de perfil não precisam da mesma resolução de um banner/fundo.
        url_publica = processar_e_salvar_imagem(request.files["arquivo"], max_dim=512)
    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    current_user.foto_url = url_publica
    db.session.commit()
    return jsonify(current_user.to_dict()), 201


@auth_bp.put("/tema")
@login_required
def atualizar_tema():
    """Guarda a preferência de tema (claro/escuro) no próprio usuário, para
    que ela acompanhe a pessoa entre dispositivos — funciona tanto para
    usuários comuns quanto para admins."""
    payload = request.get_json(silent=True) or {}
    try:
        data = TemaIn(**payload)
    except ValidationError as exc:
        return jsonify({"error": exc.errors()[0]["msg"].replace("Value error, ", "")}), 400

    current_user.tema = TemaPreferencia(data.tema)
    db.session.commit()
    return jsonify(current_user.to_dict())
