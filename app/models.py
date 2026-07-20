import enum
from datetime import datetime, timedelta, timezone

from flask_login import UserMixin
from sqlalchemy.exc import IntegrityError
from werkzeug.security import generate_password_hash, check_password_hash

from app.extensions import db


def utcnow():
    return datetime.now(timezone.utc)


# ------------------------------------------------------------------
# ENUMS (espelham as strings usadas no front-end Alpine.js)
# ------------------------------------------------------------------
class PerfilCidade(str, enum.Enum):
    matriz = "matriz"
    filial = "filial"


class ModoPrazo(str, enum.Enum):
    periodo = "periodo"       # datas (sem hora)
    dataHora = "dataHora"     # data + hora
    semData = "semData"       # sem limite de data, só regra


class TipoAberturaFDS(str, enum.Enum):
    normal = "normal"
    emergencia = "emergencia"
    fechado = "fechado"


class ModoDuracaoAviso(str, enum.Enum):
    dias = "dias"
    horas = "horas"


class StatusAviso(str, enum.Enum):
    aguardando = "Aguardando"
    ativo = "Ativo"
    expirado = "Expirado"


class RoleUsuario(str, enum.Enum):
    admin = "admin"
    usuario = "usuario"


class StatusUsuario(str, enum.Enum):
    pendente = "pendente"
    aprovado = "aprovado"
    reprovado = "reprovado"


class TemaPreferencia(str, enum.Enum):
    escuro = "escuro"
    claro = "claro"


class TipoAviso(str, enum.Enum):
    informativo = "informativo"
    atencao = "atencao"
    urgente = "urgente"


# ------------------------------------------------------------------
# USER (Flask-Login)
# ------------------------------------------------------------------
class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_active_flag = db.Column("is_active", db.Boolean, default=True, nullable=False)

    role = db.Column(db.Enum(RoleUsuario), nullable=False, default=RoleUsuario.usuario)
    status = db.Column(db.Enum(StatusUsuario), nullable=False, default=StatusUsuario.pendente)

    # -------- Perfil (personalização própria do usuário) --------
    nome = db.Column(db.String(120), nullable=True)
    foto_url = db.Column(db.String(255), nullable=True)
    tema = db.Column(db.Enum(TemaPreferencia), nullable=False, default=TemaPreferencia.escuro)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    def set_password(self, password: str) -> None:
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

    @property
    def is_active(self):
        return self.is_active_flag

    @property
    def is_admin(self) -> bool:
        return self.role == RoleUsuario.admin

    @property
    def pode_acessar(self) -> bool:
        """Admin sempre pode; usuário comum só depois de aprovado."""
        return self.is_admin or self.status == StatusUsuario.aprovado

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "nome": self.nome or "",
            "fotoUrl": self.foto_url,
            "tema": self.tema.value if self.tema else "escuro",
            "role": self.role.value,
            "status": self.status.value,
            "criadoEm": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<User {self.username}>"


# ------------------------------------------------------------------
# SESSÃO DE USUÁRIO (um registro por login bem-sucedido / dispositivo)
# ------------------------------------------------------------------
class SessaoUsuario(db.Model):
    """Registro de cada login bem-sucedido (um por dispositivo/navegador).

    Por que essa tabela existe: o cookie de sessão do Flask (Flask-Session)
    já isola cada navegador/dispositivo por si só — cada um recebe um
    identificador de sessão aleatório, assinado e guardado só no lado do
    servidor.

    Esta tabela adiciona uma SEGUNDA camada de validação, totalmente
    independente do cookie: a cada requisição autenticada, o app confere se
    o token guardado dentro da sessão do servidor corresponde a um registro
    aqui, ainda não revogado, e pertencente exatamente ao mesmo usuário que
    o Flask-Login diz estar logado (ver app/auth/guard.py). Qualquer
    divergência — por exemplo uma resposta antiga reaproveitada por engano
    por algum cache/proxy no meio do caminho, ou uma sessão encerrada em
    outro lugar — derruba a sessão imediatamente, em vez de arriscar
    mostrar a conta de uma pessoa para outra.

    De brinde, isso também dá suporte a "múltiplas sessões simultâneas":
    o mesmo usuário pode estar logado em vários dispositivos ao mesmo
    tempo, cada um com seu próprio registro aqui, podendo ver e encerrar
    sessões individualmente (ver /api/auth/sessoes).
    """

    __tablename__ = "sessoes_usuario"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    token = db.Column(db.String(64), unique=True, nullable=False, index=True)

    user_agent = db.Column(db.String(255), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    last_seen_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    revoked_at = db.Column(db.DateTime(timezone=True), nullable=True)

    usuario = db.relationship("User", foreign_keys=[user_id])

    def to_dict(self, atual: bool = False):
        return {
            "id": self.id,
            "userAgent": self.user_agent or "",
            "ip": self.ip_address or "",
            "criadoEm": self.created_at.isoformat() if self.created_at else None,
            "ultimoAcesso": self.last_seen_at.isoformat() if self.last_seen_at else None,
            "atual": atual,
        }

    def __repr__(self):
        return f"<SessaoUsuario {self.id} user={self.user_id}>"


# ------------------------------------------------------------------
# CIDADE
# ------------------------------------------------------------------
class Cidade(db.Model):
    __tablename__ = "cidades"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(120), nullable=False, index=True)
    perfil = db.Column(db.Enum(PerfilCidade), nullable=False, default=PerfilCidade.matriz)

    modo_prazo = db.Column(db.Enum(ModoPrazo), nullable=False, default=ModoPrazo.semData)
    # Guardamos como string para preservar exatamente o formato enviado pelo
    # front (YYYY-MM-DD para 'periodo' e YYYY-MM-DDTHH:MM para 'dataHora').
    prazo_inicio = db.Column(db.String(20), nullable=True)
    prazo_fim = db.Column(db.String(20), nullable=True)

    regra_horas = db.Column(db.String(255), nullable=True)
    observacao = db.Column(db.Text, nullable=True)

    tecnicos_fim_semana = db.Column(db.Boolean, default=False, nullable=False)
    tipo_abertura_fim_semana = db.Column(
        db.Enum(TipoAberturaFDS), nullable=False, default=TipoAberturaFDS.normal
    )
    plantonista_fds = db.Column(db.String(120), nullable=True)
    modo_auto_plantonista = db.Column(db.Boolean, default=False, nullable=False)

    imagem_url = db.Column(db.String(255), nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @property
    def modo_prazo_value(self):
        return self.modo_prazo.value

    @property
    def tipo_abertura_value(self):
        return self.tipo_abertura_fim_semana.value

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "perfil": self.perfil.value,
            "modoPrazo": self.modo_prazo.value,
            "prazoInicio": self.prazo_inicio or "",
            "prazoFim": self.prazo_fim or "",
            "regraHoras": self.regra_horas or "",
            "observacao": self.observacao or "",
            "tecnicosFimSemana": self.tecnicos_fim_semana,
            "tipoAberturaFimSemana": self.tipo_abertura_fim_semana.value,
            "plantonistaFDS": self.plantonista_fds or "",
            "modoAutoPlantonista": self.modo_auto_plantonista,
            "imagemUrl": self.imagem_url,
        }

    def __repr__(self):
        return f"<Cidade {self.nome}>"


# ------------------------------------------------------------------
# AVISO
# ------------------------------------------------------------------
class Aviso(db.Model):
    __tablename__ = "avisos"

    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(160), nullable=False)
    descricao = db.Column(db.Text, nullable=True)
    tipo = db.Column(db.Enum(TipoAviso), nullable=False, default=TipoAviso.informativo)

    autor_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    imagem_url = db.Column(db.String(255), nullable=True)

    modo_duracao = db.Column(db.Enum(ModoDuracaoAviso), nullable=False, default=ModoDuracaoAviso.dias)
    # 'dias'  -> inicio/fim = 'YYYY-MM-DD'
    # 'horas' -> inicio = 'YYYY-MM-DDTHH:MM', fim vazio, duracao_horas obrigatório
    inicio = db.Column(db.String(20), nullable=False)
    fim = db.Column(db.String(20), nullable=True)
    duracao_horas = db.Column(db.Float, nullable=True)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    autor = db.relationship("User", foreign_keys=[autor_id])

    @property
    def modo_duracao_value(self):
        return self.modo_duracao.value

    def calcular_status(self) -> str:
        """Recalcula o status (Aguardando/Ativo/Expirado) com base no relógio atual,
        replicando a lógica 'obterRangeAviso' + 'atualizarStatusAvisos' do front."""
        inicio_dt, fim_dt = self._range()
        if inicio_dt is None or fim_dt is None:
            return StatusAviso.aguardando.value
        agora = datetime.now(timezone.utc) if inicio_dt.tzinfo else datetime.now()
        if agora < inicio_dt:
            return StatusAviso.aguardando.value
        if inicio_dt <= agora <= fim_dt:
            return StatusAviso.ativo.value
        return StatusAviso.expirado.value

    def _range(self):
        try:
            if self.modo_duracao == ModoDuracaoAviso.horas:
                inicio_dt = datetime.fromisoformat(self.inicio)
                horas = self.duracao_horas or 0
                fim_dt = inicio_dt + timedelta(hours=horas)
                return inicio_dt, fim_dt
            inicio_dt = datetime.fromisoformat(self.inicio + "T00:00:00")
            fim_dt = datetime.fromisoformat((self.fim or self.inicio) + "T23:59:59")
            return inicio_dt, fim_dt
        except (ValueError, TypeError):
            return None, None

    def to_dict(self):
        return {
            "id": self.id,
            "titulo": self.titulo,
            "descricao": self.descricao or "",
            "tipo": self.tipo.value if self.tipo else "informativo",
            "imagemUrl": self.imagem_url,
            "autorId": self.autor_id,
            "autorNome": (self.autor.nome or self.autor.username) if self.autor else "Administração",
            "modoDuracao": self.modo_duracao.value,
            "inicio": self.inicio,
            "fim": self.fim or "",
            "duracaoHoras": self.duracao_horas,
            "status": self.calcular_status(),
        }

    def __repr__(self):
        return f"<Aviso {self.titulo}>"


# ------------------------------------------------------------------
# GRUPOS DE CHAT (canais/salas temáticas — organizam a conversa em vez de
# jogar tudo num único chat geral)
# ------------------------------------------------------------------
class GrupoChat(db.Model):
    __tablename__ = "grupos_chat"

    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(80), nullable=False)
    descricao = db.Column(db.String(255), nullable=True)
    icone = db.Column(db.String(40), nullable=False, default="fa-users")
    cor = db.Column(db.String(20), nullable=False, default="indigo")

    criado_por_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    criador = db.relationship("User", foreign_keys=[criado_por_id])
    membros = db.relationship(
        "GrupoChatMembro", back_populates="grupo", cascade="all, delete-orphan"
    )

    def to_dict(self, current_user_id=None):
        membros_atuais = list(self.membros)
        sou_membro = any(m.user_id == current_user_id for m in membros_atuais)
        sou_admin_grupo = any(
            m.user_id == current_user_id and m.papel == "admin" for m in membros_atuais
        )
        return {
            "id": self.id,
            "nome": self.nome,
            "descricao": self.descricao or "",
            "icone": self.icone,
            "cor": self.cor,
            "criadoPorId": self.criado_por_id,
            "criadoPorNome": (self.criador.nome or self.criador.username) if self.criador else None,
            "totalMembros": len(membros_atuais),
            "souMembro": sou_membro,
            "souAdminDoGrupo": sou_admin_grupo,
            "criadoEm": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self):
        return f"<GrupoChat {self.id} {self.nome!r}>"


class GrupoChatMembro(db.Model):
    __tablename__ = "grupos_chat_membros"
    __table_args__ = (db.UniqueConstraint("grupo_id", "user_id", name="uq_grupo_membro"),)

    id = db.Column(db.Integer, primary_key=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_chat.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    papel = db.Column(db.String(20), nullable=False, default="membro")  # 'admin' | 'membro'
    joined_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False)

    grupo = db.relationship("GrupoChat", back_populates="membros")
    usuario = db.relationship("User", foreign_keys=[user_id])


# ------------------------------------------------------------------
# CHAT INTERNO (área pública, apenas usuários aprovados)
# ------------------------------------------------------------------
class ChatMessage(db.Model):
    __tablename__ = "chat_mensagens"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    # Exatamente um dos dois abaixo preenchido identifica o "canal" da
    # mensagem; os dois em branco = chat geral (visível a todos aprovados).
    destinatario_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True, index=True)
    grupo_id = db.Column(db.Integer, db.ForeignKey("grupos_chat.id"), nullable=True, index=True)
    conteudo = db.Column(db.Text, nullable=False)

    created_at = db.Column(db.DateTime(timezone=True), default=utcnow, nullable=False, index=True)
    editado_em = db.Column(db.DateTime(timezone=True), nullable=True)

    autor = db.relationship("User", foreign_keys=[user_id])
    destinatario = db.relationship("User", foreign_keys=[destinatario_id])
    grupo = db.relationship("GrupoChat", foreign_keys=[grupo_id])

    def to_dict(self, current_user_id=None, is_admin=False):
        return {
            "id": self.id,
            "autorId": self.user_id,
            "autor": (self.autor.nome or self.autor.username) if self.autor else "Usuário removido",
            "autorFotoUrl": self.autor.foto_url if self.autor else None,
            "autorEhAdmin": bool(self.autor and self.autor.is_admin),
            "destinatarioId": self.destinatario_id,
            "grupoId": self.grupo_id,
            "conteudo": self.conteudo,
            "criadoEm": self.created_at.isoformat() if self.created_at else None,
            "editado": self.editado_em is not None,
            "podeEditar": current_user_id == self.user_id,
            "podeApagar": current_user_id == self.user_id or is_admin,
        }

    def __repr__(self):
        return f"<ChatMessage {self.id} de user {self.user_id}>"


# ------------------------------------------------------------------
# CONFIGURAÇÃO DA LANDING PAGE (personalização do administrador)
# ------------------------------------------------------------------
class TipoFundo(str, enum.Enum):
    nenhum = "nenhum"
    imagem = "imagem"
    video = "video"


class ConfiguracaoCards(db.Model):
    """Linha única (singleton) com a personalização dos CARDS das cidades:
    os rótulos (textos) de cada campo, e preferências visuais (tamanho de
    fonte, espaçamento, largura, colunas). NUNCA mexe nos dados cadastrados
    das cidades — só em como eles são rotulados e exibidos, permitindo
    adequar a nomenclatura à realidade de cada operação sem tocar código.
    """

    __tablename__ = "configuracao_cards"

    id = db.Column(db.Integer, primary_key=True)
    # Guardados como JSON flexível (em vez de uma coluna por rótulo) para
    # não exigir uma nova migração toda vez que se queira customizar mais
    # um texto — o dicionário de valores padrão (abaixo) preenche qualquer
    # chave que ainda não tenha sido customizada.
    rotulos = db.Column(db.JSON, nullable=False, default=dict)
    estilo = db.Column(db.JSON, nullable=False, default=dict)

    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    ROTULOS_PADRAO = {
        "perfil": "Perfil",
        "matriz": "Matriz",
        "filial": "Filial",
        "prazo": "Prazo de O.S",
        "semPrazo": "Sem prazo definido",
        "regraHoras": "Regra de Horas",
        "observacao": "Observação",
        "tecnicosFimSemana": "Técnicos no Fim de Semana",
        "aberturaFimSemana": "Abertura no Fim de Semana",
        "aberturaNormal": "Normal",
        "aberturaEmergencia": "Somente Urgências",
        "aberturaFechado": "Fechado",
        "plantonista": "Plantonista",
        "plantonistaAuto": "Plantonista Ativo (Modo Auto)",
        "situacaoNoPrazo": "No Prazo",
        "situacaoAtencao": "Atenção",
        "situacaoAtrasado": "Atrasado",
        # Textos exibidos automaticamente conforme o estado calculado da
        # cidade (não vêm de um campo cadastrado — o sistema decide qual
        # mostrar). Customizáveis para caber na realidade da operação.
        "mensagemAutoLimitado": "Agendamentos limitados para o período atual",
        "mensagemAutoLiberadoTitulo": "Canal liberado e ilimitado",
        "mensagemAutoLiberadoDetalhe": "Agendamento sem restrições de abertura.",
    }

    # Todos os blocos de informação que podem aparecer no card/detalhe da
    # cidade. A ORDEM da lista em estilo['campos'] é a ordem de exibição;
    # um campo ausente da lista fica OCULTO — dá controle total (esconder,
    # reordenar) sobre o que aparece automaticamente para cada operação.
    CAMPOS_DISPONIVEIS = ["clima", "prazo", "regraHoras", "plantao", "observacao", "mensagemAutomatica"]

    ESTILO_PADRAO = {
        "tamanhoFonte": "md",     # sm | md | lg
        "espacamento": "normal",  # compacto | normal | espacoso
        "largura": "md",          # sm | md | lg | xl
        "colunas": "auto",        # auto | 1 | 2 | 3 | 4
        "campos": list(CAMPOS_DISPONIVEIS),  # ordem + visibilidade dos blocos de informação
    }

    @classmethod
    def obter(cls) -> "ConfiguracaoCards":
        config = cls.query.get(1)
        if config is not None:
            return config
        # Primeira vez que alguém acessa isso no sistema: cria a linha
        # única. Sob carga concorrente, duas requisições podem chegar
        # aqui ao mesmo tempo e ambas tentarem criar id=1 — a segunda vai
        # bater na constraint de chave primária. Não é um erro real, só
        # uma corrida de inicialização; tratamos como "a outra já criou,
        # então só leio o que ela criou".
        config = cls(id=1, rotulos={}, estilo={})
        db.session.add(config)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            config = cls.query.get(1)
        return config

    def to_dict(self):
        return {
            "rotulos": {**self.ROTULOS_PADRAO, **(self.rotulos or {})},
            "estilo": {**self.ESTILO_PADRAO, **(self.estilo or {})},
        }

    def __repr__(self):
        return "<ConfiguracaoCards>"


class ConfiguracaoSite(db.Model):
    """Linha única (singleton) com a personalização da landing page pública
    — nome da empresa, textos e imagem/vídeo de fundo, tudo editável pelo
    administrador. Visitantes não autenticados só veem esta tela."""

    __tablename__ = "configuracao_site"

    id = db.Column(db.Integer, primary_key=True)

    nome_empresa = db.Column(db.String(120), nullable=False, default="SCA Control")
    slogan = db.Column(db.String(200), nullable=False, default="Sistema de Cidades e Avisos")
    descricao = db.Column(db.Text, nullable=True, default="")

    tipo_fundo = db.Column(db.Enum(TipoFundo), nullable=False, default=TipoFundo.nenhum)
    imagem_fundo_url = db.Column(db.String(255), nullable=True)
    video_fundo_url = db.Column(db.String(255), nullable=True)

    # Fundo da TELA DE LOGIN — independente do fundo da landing page acima
    # (a pessoa pode querer, por exemplo, uma imagem na página inicial e um
    # vídeo diferente — ou nenhum — na tela de entrar/cadastrar).
    tipo_fundo_login = db.Column(db.Enum(TipoFundo), nullable=False, default=TipoFundo.nenhum)
    imagem_fundo_login_url = db.Column(db.String(255), nullable=True)
    video_fundo_login_url = db.Column(db.String(255), nullable=True)
    logo_url = db.Column(db.String(255), nullable=True)
    cor_destaque = db.Column(db.String(7), nullable=False, default="#4f46e5")

    updated_at = db.Column(db.DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    @classmethod
    def obter(cls) -> "ConfiguracaoSite":
        """Sempre há exatamente uma linha (id=1). Cria com valores padrão
        na primeira vez que for acessada, se ainda não existir — de forma
        segura mesmo se duas requisições chegarem simultaneamente nesse
        primeiro acesso (ver comentário equivalente em ConfiguracaoCards.obter)."""
        config = cls.query.get(1)
        if config is not None:
            return config
        config = cls(id=1)
        db.session.add(config)
        try:
            db.session.commit()
        except IntegrityError:
            db.session.rollback()
            config = cls.query.get(1)
        return config

    def to_dict(self):
        return {
            "nomeEmpresa": self.nome_empresa,
            "slogan": self.slogan,
            "descricao": self.descricao or "",
            "tipoFundo": self.tipo_fundo.value,
            "imagemFundoUrl": self.imagem_fundo_url,
            "videoFundoUrl": self.video_fundo_url,
            "tipoFundoLogin": self.tipo_fundo_login.value,
            "imagemFundoLoginUrl": self.imagem_fundo_login_url,
            "videoFundoLoginUrl": self.video_fundo_login_url,
            "logoUrl": self.logo_url,
            "corDestaque": self.cor_destaque,
        }

    def __repr__(self):
        return f"<ConfiguracaoSite {self.nome_empresa}>"
