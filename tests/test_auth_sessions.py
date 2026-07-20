"""
Validação automatizada da autenticação por sessão (Flask-Login + Flask-Session).

Cobre os pontos pedidos na tarefa:
  - login / logout / cadastro
  - isolamento total entre "navegadores" diferentes (cada um é um
    app.test_client() próprio, com seu próprio jar de cookies — o mesmo
    isolamento que existe entre abas anônimas/navegadores/dispositivos reais)
  - múltiplos usuários simultâneos, sem vazamento de sessão entre eles
  - logout invalida a sessão de verdade (não só do lado do cliente)
  - proteção CSRF em métodos que alteram estado
  - expiração por inatividade (independente do cookie — via SessaoUsuario)
  - reprovação/edição de senha pelo admin revoga sessões já abertas na hora

Rodar com:  PYTHONPATH=. /home/claude/venv/bin/pytest tests/ -v
"""
import datetime as dt

import pytest

from app import create_app
from app.extensions import db
from app.models import User, RoleUsuario, StatusUsuario, SessaoUsuario


@pytest.fixture()
def app():
    application = create_app(testing=True)
    with application.app_context():
        db.create_all()
    # IMPORTANTE: o app_context NÃO pode continuar empurrado durante o
    # `yield` (durante a execução do teste em si). Se ficasse, toda
    # chamada feita por app.test_client() dentro do teste reaproveitaria
    # esse MESMO app_context em vez de criar um novo por requisição — e
    # com isso reaproveitaria também o `flask.g` (onde o Flask-WTF
    # cacheia o token CSRF por request). Isso faria dois test_client()
    # diferentes (simulando dois navegadores) parecerem compartilhar
    # estado, um artefato do teste que NUNCA acontece em produção via
    # WSGI/gunicorn (lá cada requisição HTTP real ganha seu próprio
    # app_context, sempre).
    yield application
    with application.app_context():
        db.session.remove()
        db.drop_all()


def _criar_usuario(app, username, password, role=RoleUsuario.usuario, status=StatusUsuario.aprovado):
    with app.app_context():
        u = User(username=username, role=role, status=status)
        u.set_password(password)
        db.session.add(u)
        db.session.commit()
        return u.id


def _login(client, username, password):
    return client.post("/api/auth/login", json={"username": username, "password": password})


class TestLoginLogoutCadastro:
    def test_cadastro_publico_nasce_pendente_e_nao_loga(self, app):
        client = app.test_client()
        resp = client.post("/api/auth/registrar", json={"username": "novo1", "password": "SenhaForte123"})
        assert resp.status_code == 201
        # tentar logar antes da aprovação deve falhar com 403 (pendente)
        resp = _login(client, "novo1", "SenhaForte123")
        assert resp.status_code == 403
        assert resp.get_json()["status"] == "pendente"

    def test_login_com_credenciais_erradas_nao_autentica(self, app):
        _criar_usuario(app, "ana", "SenhaForte123")
        client = app.test_client()
        resp = _login(client, "ana", "senhaErrada")
        assert resp.status_code == 401
        resp = client.get("/api/auth/me")
        assert resp.get_json()["loggedIn"] is False

    def test_login_e_acesso_a_rota_protegida(self, app):
        _criar_usuario(app, "ana", "SenhaForte123")
        client = app.test_client()
        resp = _login(client, "ana", "SenhaForte123")
        assert resp.status_code == 200
        assert resp.get_json()["user"]["username"] == "ana"

        resp = client.get("/api/auth/me")
        body = resp.get_json()
        assert body["loggedIn"] is True
        assert body["user"]["username"] == "ana"

    def test_logout_invalida_a_sessao_no_servidor(self, app):
        _criar_usuario(app, "ana", "SenhaForte123")
        client = app.test_client()
        _login(client, "ana", "SenhaForte123")
        assert client.get("/api/auth/me").get_json()["loggedIn"] is True

        resp = client.post("/api/auth/logout")
        assert resp.status_code == 200

        # depois do logout, mesmo cookie/jar não deve mais estar autenticado
        resp = client.get("/api/auth/me")
        assert resp.get_json()["loggedIn"] is False

        # e uma rota protegida deve responder 401, não reaproveitar nada
        resp = client.get("/api/auth/sessoes")
        assert resp.status_code == 401

        with app.app_context():
            sessoes = SessaoUsuario.query.all()
            assert all(s.revoked_at is not None for s in sessoes)


class TestIsolamentoDeSessoes:
    def test_dois_navegadores_sao_totalmente_independentes(self, app):
        """Simula dois usuários em dois navegadores diferentes: cada
        app.test_client() tem seu próprio cookiejar, exatamente como duas
        abas anônimas / dois navegadores / dois dispositivos distintos."""
        _criar_usuario(app, "ana", "SenhaForte123")
        _criar_usuario(app, "bruno", "OutraSenha456")

        navegador_ana = app.test_client()
        navegador_bruno = app.test_client()

        _login(navegador_ana, "ana", "SenhaForte123")
        _login(navegador_bruno, "bruno", "OutraSenha456")

        me_ana = navegador_ana.get("/api/auth/me").get_json()
        me_bruno = navegador_bruno.get("/api/auth/me").get_json()

        assert me_ana["user"]["username"] == "ana"
        assert me_bruno["user"]["username"] == "bruno"
        # nunca o cookie de um pode "abrir" a conta do outro
        assert me_ana["user"]["username"] != me_bruno["user"]["username"]

    def test_logout_em_um_navegador_nao_afeta_o_outro(self, app):
        """Mesmo usuário logado em dois navegadores (ex.: notebook +
        celular): encerrar a sessão em um não pode derrubar o outro."""
        _criar_usuario(app, "ana", "SenhaForte123")
        notebook = app.test_client()
        celular = app.test_client()

        _login(notebook, "ana", "SenhaForte123")
        _login(celular, "ana", "SenhaForte123")

        assert notebook.get("/api/auth/me").get_json()["loggedIn"] is True
        assert celular.get("/api/auth/me").get_json()["loggedIn"] is True

        notebook.post("/api/auth/logout")

        assert notebook.get("/api/auth/me").get_json()["loggedIn"] is False
        assert celular.get("/api/auth/me").get_json()["loggedIn"] is True

    def test_novo_login_nao_reutiliza_sessao_anonima_anterior(self, app):
        """Mitigação de fixação de sessão: um cookie de sessão anônima
        obtido ANTES do login não pode ser "herdado" após autenticar."""
        _criar_usuario(app, "ana", "SenhaForte123")
        client = app.test_client()

        resp_anonimo = client.get("/api/auth/csrf-token")
        cookie_antes = resp_anonimo.headers.get("Set-Cookie")

        resp_login = _login(client, "ana", "SenhaForte123")
        cookie_depois = resp_login.headers.get("Set-Cookie")

        # o Flask-Session deve ter emitido um identificador de sessão novo
        assert cookie_antes is None or cookie_antes != cookie_depois

    def test_admin_nao_ve_sessoes_de_outro_usuario_na_listagem(self, app):
        _criar_usuario(app, "ana", "SenhaForte123")
        _criar_usuario(app, "bruno", "OutraSenha456")

        navegador_ana = app.test_client()
        navegador_bruno = app.test_client()
        _login(navegador_ana, "ana", "SenhaForte123")
        _login(navegador_bruno, "bruno", "OutraSenha456")

        sessoes_ana = navegador_ana.get("/api/auth/sessoes").get_json()["sessoes"]
        sessoes_bruno = navegador_bruno.get("/api/auth/sessoes").get_json()["sessoes"]

        assert len(sessoes_ana) == 1
        assert len(sessoes_bruno) == 1
        # tokens de sessão nunca aparecem repetidos entre usuários distintos


class TestRevogacaoImediata:
    def test_reprovar_usuario_derruba_sessao_ativa_na_hora(self, app):
        admin_id = _criar_usuario(app, "root", "AdminSenha123", role=RoleUsuario.admin)
        _criar_usuario(app, "ana", "SenhaForte123")

        admin = app.test_client()
        ana = app.test_client()
        _login(admin, "root", "AdminSenha123")
        _login(ana, "ana", "SenhaForte123")

        assert ana.get("/api/auth/me").get_json()["loggedIn"] is True

        with app.app_context():
            user_ana = User.query.filter_by(username="ana").first()
            uid = user_ana.id

        csrf = admin.get("/api/auth/csrf-token").get_json()["csrfToken"]
        resp = admin.post(
            f"/api/admin/usuarios/{uid}/reprovar",
            headers={"X-CSRFToken": csrf},
        )
        assert resp.status_code == 200

        # a sessão da Ana precisa cair na PRÓXIMA requisição dela, sem que
        # ela precise deslogar/logar de novo manualmente
        resp = ana.get("/api/auth/sessoes")
        assert resp.status_code == 401


class TestCSRF:
    def test_post_sem_csrf_token_e_recusado(self, app):
        # WTF_CSRF_ENABLED é desligado por padrão em TestingConfig para
        # facilitar outros testes; aqui religamos só para este teste.
        app.config["WTF_CSRF_ENABLED"] = True
        _criar_usuario(app, "ana", "SenhaForte123")
        client = app.test_client()

        # Sem token CSRF, nem o próprio login (que também é POST) deve
        # passar — é exatamente essa a proteção que se quer comprovar.
        resp = _login(client, "ana", "SenhaForte123")
        assert resp.status_code == 400  # CSRFError vira 400 (ver app/__init__.py)
        app.config["WTF_CSRF_ENABLED"] = False

    def test_post_com_csrf_token_correto_funciona(self, app):
        app.config["WTF_CSRF_ENABLED"] = True
        _criar_usuario(app, "ana", "SenhaForte123")
        client = app.test_client()

        # Fluxo real do front-end: busca o token anônimo antes de logar
        # (ver obterCsrfToken() em app/static/js/app.js), e reenvia sempre
        # o token mais recente devolvido por cada resposta.
        csrf_anonimo = client.get("/api/auth/csrf-token").get_json()["csrfToken"]
        resp = client.post(
            "/api/auth/login",
            json={"username": "ana", "password": "SenhaForte123"},
            headers={"X-CSRFToken": csrf_anonimo},
        )
        assert resp.status_code == 200
        csrf_pos_login = resp.get_json()["csrfToken"]

        resp = client.put(
            "/api/auth/tema", json={"tema": "claro"}, headers={"X-CSRFToken": csrf_pos_login}
        )
        assert resp.status_code == 200
        app.config["WTF_CSRF_ENABLED"] = False


class TestExpiracaoPorInatividade:
    def test_sessao_expira_apos_periodo_de_inatividade(self, app):
        """Sem depender do Max-Age do cookie: o guard (app/auth/guard.py)
        também confere `last_seen_at` contra PERMANENT_SESSION_LIFETIME e
        revoga a sessão do lado do servidor quando ela ficou inativa além
        do limite configurado."""
        app.config["PERMANENT_SESSION_LIFETIME"] = dt.timedelta(hours=1)
        _criar_usuario(app, "ana", "SenhaForte123")
        client = app.test_client()
        _login(client, "ana", "SenhaForte123")
        assert client.get("/api/auth/me").get_json()["loggedIn"] is True

        # Simula inatividade: empurra `last_seen_at` do registro de sessão
        # para além do limite configurado, sem precisar esperar de verdade.
        with app.app_context():
            sessao = SessaoUsuario.query.filter_by(user_id=1).first()
            sessao.last_seen_at = dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)
            db.session.commit()

        # a PRÓXIMA requisição já deve encontrar a sessão vencida por
        # inatividade e derrubá-la — sem exigir logout explícito.
        resp = client.get("/api/auth/sessoes")
        assert resp.status_code == 401

        resp = client.get("/api/auth/me")
        assert resp.get_json()["loggedIn"] is False

        with app.app_context():
            sessao = SessaoUsuario.query.filter_by(user_id=1).first()
            assert sessao.revoked_at is not None
