"""
Camada de validação/serialização.

- Pydantic  -> valida o payload JSON que chega nas rotas da API (entrada).
- Marshmallow -> serializa os modelos SQLAlchemy para JSON (saída), com
  campos calculados (ex.: status do aviso).

Mantemos os dois propositalmente, conforme solicitado no stack do projeto.
"""
from typing import Optional
from pydantic import BaseModel, field_validator, model_validator
from marshmallow import Schema, fields, validate


# ------------------------------------------------------------------
# PYDANTIC — validação de entrada
# ------------------------------------------------------------------
class CidadeIn(BaseModel):
    nome: str
    perfil: str = "matriz"
    modoPrazo: str = "semData"
    prazoInicio: Optional[str] = ""
    prazoFim: Optional[str] = ""
    regraHoras: Optional[str] = ""
    observacao: Optional[str] = ""
    tecnicosFimSemana: bool = False
    tipoAberturaFimSemana: str = "normal"
    plantonistaFDS: Optional[str] = ""
    modoAutoPlantonista: bool = False
    imagemUrl: Optional[str] = None

    @field_validator("nome")
    @classmethod
    def nome_nao_vazio(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Informe o nome da cidade.")
        if len(v) > 120:
            raise ValueError("Nome da cidade muito longo (máx. 120 caracteres).")
        return v

    @field_validator("perfil")
    @classmethod
    def perfil_valido(cls, v: str) -> str:
        if v not in ("matriz", "filial"):
            raise ValueError("Perfil operacional inválido.")
        return v

    @field_validator("modoPrazo")
    @classmethod
    def modo_prazo_valido(cls, v: str) -> str:
        if v not in ("periodo", "dataHora", "semData"):
            raise ValueError("Modo de prazo inválido.")
        return v

    @field_validator("tipoAberturaFimSemana")
    @classmethod
    def abertura_fds_valida(cls, v: str) -> str:
        if v not in ("normal", "emergencia", "fechado"):
            raise ValueError("Tipo de abertura de fim de semana inválido.")
        return v

    @model_validator(mode="after")
    def valida_datas(self):
        if self.modoPrazo != "semData":
            if not self.prazoInicio or not self.prazoFim:
                raise ValueError(
                    "Defina o início e o fim do prazo operacional para esta localidade."
                )
            if self.prazoFim < self.prazoInicio:
                raise ValueError(
                    "A data/hora de fim do prazo não pode ser anterior à de início."
                )
        return self


class AvisoIn(BaseModel):
    titulo: str
    descricao: Optional[str] = ""
    tipo: str = "informativo"
    imagemUrl: Optional[str] = None
    modoDuracao: str = "dias"
    inicio: Optional[str] = ""
    fim: Optional[str] = ""
    duracaoHoras: Optional[float] = None

    @field_validator("titulo")
    @classmethod
    def titulo_nao_vazio(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Informe o título do aviso.")
        if len(v) > 160:
            raise ValueError("Título muito longo (máx. 160 caracteres).")
        return v

    @field_validator("tipo")
    @classmethod
    def tipo_valido(cls, v: str) -> str:
        if v not in ("informativo", "atencao", "urgente"):
            raise ValueError("Tipo de aviso inválido.")
        return v

    @field_validator("modoDuracao")
    @classmethod
    def modo_duracao_valido(cls, v: str) -> str:
        if v not in ("dias", "horas"):
            raise ValueError("Modo de duração inválido.")
        return v

    @model_validator(mode="after")
    def valida_vigencia(self):
        if self.modoDuracao == "dias":
            # Só no modo "período (dias)" a pessoa escolhe as datas; no
            # modo "duração em horas" a contagem sempre começa agora,
            # calculada pelo servidor (ver _aviso_from_payload em
            # app/api/avisos.py) — não depende do que vier do cliente aqui.
            if not self.inicio:
                raise ValueError("Defina a data de início da vigência.")
            if not self.fim:
                raise ValueError("Defina as datas de início e fim da vigência.")
            if self.fim < self.inicio:
                raise ValueError("A data de fim não pode ser anterior à data de início.")
        else:
            if not self.duracaoHoras or self.duracaoHoras <= 0:
                raise ValueError("Informe uma duração em horas maior que zero.")
        return self


class LoginIn(BaseModel):
    username: str
    password: str
    # Opt-in explícito do usuário para manter a sessão viva entre fechamentos
    # do navegador (cookie persistente por alguns dias). Por padrão é False:
    # a sessão vale apenas enquanto o navegador estiver aberto, para que um
    # computador/navegador compartilhado por várias pessoas nunca autologue
    # a próxima pessoa como quem usou por último.
    manterConectado: bool = False

    @field_validator("username", "password")
    @classmethod
    def nao_vazio(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("Preencha usuário e senha para acessar.")
        return v


class RegistroIn(BaseModel):
    username: str
    password: str

    @field_validator("username")
    @classmethod
    def username_valido(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if len(v) < 3:
            raise ValueError("O usuário deve ter pelo menos 3 caracteres.")
        if len(v) > 60:
            raise ValueError("Usuário muito longo (máx. 60 caracteres).")
        if not all(c.isalnum() or c in "._-" for c in v):
            raise ValueError("Use apenas letras, números, ponto, traço ou underline no usuário.")
        return v

    @field_validator("password")
    @classmethod
    def senha_valida(cls, v: str) -> str:
        if not v or len(v) < 6:
            raise ValueError("A senha deve ter pelo menos 6 caracteres.")
        if len(v) > 128:
            raise ValueError("Senha muito longa (máx. 128 caracteres).")
        return v


class UsuarioAdminIn(BaseModel):
    """Usado pelo admin para editar usuário/senha/papel de um cadastro existente."""

    username: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None

    @field_validator("username")
    @classmethod
    def username_valido(cls, v):
        if v is None or v == "":
            return v
        v = v.strip().lower()
        if len(v) < 3:
            raise ValueError("O usuário deve ter pelo menos 3 caracteres.")
        if not all(c.isalnum() or c in "._-" for c in v):
            raise ValueError("Use apenas letras, números, ponto, traço ou underline no usuário.")
        return v

    @field_validator("password")
    @classmethod
    def senha_valida(cls, v):
        if v is None or v == "":
            return v
        if len(v) < 6:
            raise ValueError("A senha deve ter pelo menos 6 caracteres.")
        return v

    @field_validator("role")
    @classmethod
    def role_valida(cls, v):
        if v is None or v == "":
            return v
        if v not in ("admin", "usuario"):
            raise ValueError("Papel de usuário inválido.")
        return v


class NovoUsuarioAdminIn(BaseModel):
    """Usado pelo admin para CRIAR um novo cadastro diretamente (sem passar
    pelo fluxo de auto-registro + aprovação) — já nasce aprovado, e pode
    nascer com papel de administrador."""

    username: str
    password: str
    role: str = "usuario"

    @field_validator("username")
    @classmethod
    def username_valido(cls, v: str) -> str:
        v = (v or "").strip().lower()
        if len(v) < 3:
            raise ValueError("O usuário deve ter pelo menos 3 caracteres.")
        if len(v) > 60:
            raise ValueError("Usuário muito longo (máx. 60 caracteres).")
        if not all(c.isalnum() or c in "._-" for c in v):
            raise ValueError("Use apenas letras, números, ponto, traço ou underline no usuário.")
        return v

    @field_validator("password")
    @classmethod
    def senha_valida(cls, v: str) -> str:
        if not v or len(v) < 6:
            raise ValueError("A senha deve ter pelo menos 6 caracteres.")
        if len(v) > 128:
            raise ValueError("Senha muito longa (máx. 128 caracteres).")
        return v

    @field_validator("role")
    @classmethod
    def role_valida(cls, v: str) -> str:
        if v not in ("admin", "usuario"):
            raise ValueError("Papel de usuário inválido.")
        return v


class PerfilIn(BaseModel):
    """Edição do próprio perfil: nome de exibição e, opcionalmente, troca
    de senha (exige a senha atual)."""

    nome: Optional[str] = ""
    senhaAtual: Optional[str] = None
    novaSenha: Optional[str] = None

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v):
        v = (v or "").strip()
        if len(v) > 120:
            raise ValueError("Nome muito longo (máx. 120 caracteres).")
        return v

    @model_validator(mode="after")
    def valida_troca_senha(self):
        if self.novaSenha:
            if not self.senhaAtual:
                raise ValueError("Informe sua senha atual para definir uma nova senha.")
            if len(self.novaSenha) < 6:
                raise ValueError("A nova senha deve ter pelo menos 6 caracteres.")
            if len(self.novaSenha) > 128:
                raise ValueError("Nova senha muito longa (máx. 128 caracteres).")
        return self


class TemaIn(BaseModel):
    tema: str

    @field_validator("tema")
    @classmethod
    def tema_valido(cls, v: str) -> str:
        if v not in ("claro", "escuro"):
            raise ValueError("Tema inválido.")
        return v


class ChatMensagemIn(BaseModel):
    conteudo: str
    destinatarioId: Optional[int] = None
    grupoId: Optional[int] = None

    @field_validator("conteudo")
    @classmethod
    def conteudo_valido(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Escreva uma mensagem antes de enviar.")
        if len(v) > 2000:
            raise ValueError("Mensagem muito longa (máx. 2000 caracteres).")
        return v


class GrupoChatIn(BaseModel):
    nome: str
    descricao: Optional[str] = ""
    icone: str = "fa-users"
    cor: str = "indigo"
    membrosIds: list[int] = []

    @field_validator("nome")
    @classmethod
    def nome_valido(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Informe o nome do grupo.")
        if len(v) > 80:
            raise ValueError("Nome muito longo (máx. 80 caracteres).")
        return v

    @field_validator("descricao")
    @classmethod
    def descricao_valida(cls, v):
        v = (v or "").strip()
        if len(v) > 255:
            raise ValueError("Descrição muito longa (máx. 255 caracteres).")
        return v

    @field_validator("icone")
    @classmethod
    def icone_valido(cls, v: str) -> str:
        permitidos = {
            "fa-users", "fa-hashtag", "fa-comments", "fa-bullhorn", "fa-briefcase",
            "fa-wrench", "fa-truck-medical", "fa-city", "fa-star", "fa-fire",
            "fa-shield-halved", "fa-code", "fa-chart-line", "fa-headset", "fa-map-location-dot",
        }
        if v not in permitidos:
            raise ValueError("Ícone inválido.")
        return v

    @field_validator("cor")
    @classmethod
    def cor_valida(cls, v: str) -> str:
        permitidas = {"indigo", "blue", "emerald", "amber", "rose", "violet", "cyan", "slate"}
        if v not in permitidas:
            raise ValueError("Cor inválida.")
        return v

    @field_validator("membrosIds")
    @classmethod
    def membros_validos(cls, v):
        if not isinstance(v, list):
            raise ValueError("Lista de membros inválida.")
        if len(v) > 200:
            raise ValueError("Grupo com muitos membros de uma vez (máx. 200).")
        return list({int(i) for i in v})


class ConfiguracaoSiteIn(BaseModel):
    nomeEmpresa: str
    slogan: Optional[str] = ""
    descricao: Optional[str] = ""
    tipoFundo: str = "nenhum"
    imagemFundoUrl: Optional[str] = None
    videoFundoUrl: Optional[str] = None
    logoUrl: Optional[str] = None
    corDestaque: Optional[str] = "#4f46e5"

    @field_validator("nomeEmpresa")
    @classmethod
    def nome_empresa_valido(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Informe o nome da empresa.")
        if len(v) > 120:
            raise ValueError("Nome da empresa muito longo (máx. 120 caracteres).")
        return v

    @field_validator("slogan")
    @classmethod
    def slogan_valido(cls, v):
        if v and len(v) > 200:
            raise ValueError("Slogan muito longo (máx. 200 caracteres).")
        return v or ""

    @field_validator("descricao")
    @classmethod
    def descricao_valida(cls, v):
        if v and len(v) > 1000:
            raise ValueError("Descrição muito longa (máx. 1000 caracteres).")
        return v or ""

    @field_validator("tipoFundo")
    @classmethod
    def tipo_fundo_valido(cls, v: str) -> str:
        if v not in ("nenhum", "imagem", "video"):
            raise ValueError("Tipo de fundo inválido.")
        return v

    @field_validator("corDestaque")
    @classmethod
    def cor_valida(cls, v):
        import re
        v = (v or "#4f46e5").strip()
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", v):
            raise ValueError("Cor de destaque inválida (use o formato #RRGGBB).")
        return v


class ConfiguracaoCardsIn(BaseModel):
    """Personalização dos cards das cidades: rótulos (textos) de cada campo
    e preferências visuais. Tudo opcional — só o que vier aqui substitui o
    valor atual (o restante permanece como estava)."""

    rotulos: dict = {}
    estilo: dict = {}

    @field_validator("rotulos")
    @classmethod
    def rotulos_validos(cls, v):
        from app.models import ConfiguracaoCards

        chaves_validas = set(ConfiguracaoCards.ROTULOS_PADRAO.keys())
        limpo = {}
        for chave, valor in (v or {}).items():
            if chave not in chaves_validas:
                continue  # ignora chaves desconhecidas, não erro — mais tolerante a versões futuras
            texto = str(valor or "").strip()
            if len(texto) > 80:
                raise ValueError(f"O texto para '{chave}' está muito longo (máx. 80 caracteres).")
            if texto:
                limpo[chave] = texto
        return limpo

    @field_validator("estilo")
    @classmethod
    def estilo_valido(cls, v):
        from app.models import ConfiguracaoCards

        opcoes = {
            "tamanhoFonte": ("sm", "md", "lg"),
            "espacamento": ("compacto", "normal", "espacoso"),
            "largura": ("sm", "md", "lg", "xl"),
            "colunas": ("auto", "1", "2", "3", "4"),
        }
        limpo = {}
        for chave, valores_aceitos in opcoes.items():
            if chave in (v or {}):
                valor = str(v[chave])
                if valor not in valores_aceitos:
                    raise ValueError(f"Valor inválido para '{chave}'.")
                limpo[chave] = valor

        if "campos" in (v or {}):
            disponiveis = set(ConfiguracaoCards.CAMPOS_DISPONIVEIS)
            campos = v["campos"]
            if not isinstance(campos, list):
                raise ValueError("Lista de campos inválida.")
            # Ignora chaves desconhecidas e duplicatas, preservando a ordem
            # enviada — o restante (campos válidos não incluídos) fica oculto.
            vistos = set()
            campos_limpos = []
            for c in campos:
                if c in disponiveis and c not in vistos:
                    campos_limpos.append(c)
                    vistos.add(c)
            limpo["campos"] = campos_limpos

        return limpo


# ------------------------------------------------------------------
# MARSHMALLOW — serialização de saída
# ------------------------------------------------------------------
class CidadeSchema(Schema):
    id = fields.Int(dump_only=True)
    nome = fields.Str()
    perfil = fields.Str()
    modoPrazo = fields.Str(attribute="modo_prazo_value")
    prazoInicio = fields.Str(attribute="prazo_inicio")
    prazoFim = fields.Str(attribute="prazo_fim")
    regraHoras = fields.Str(attribute="regra_horas")
    observacao = fields.Str()
    tecnicosFimSemana = fields.Bool(attribute="tecnicos_fim_semana")
    tipoAberturaFimSemana = fields.Str(attribute="tipo_abertura_value")
    plantonistaFDS = fields.Str(attribute="plantonista_fds")
    modoAutoPlantonista = fields.Bool(attribute="modo_auto_plantonista")
    imagemUrl = fields.Str(attribute="imagem_url")


class AvisoSchema(Schema):
    id = fields.Int(dump_only=True)
    titulo = fields.Str()
    descricao = fields.Str()
    modoDuracao = fields.Str(attribute="modo_duracao_value")
    inicio = fields.Str()
    fim = fields.Str()
    duracaoHoras = fields.Float(attribute="duracao_horas")
    status = fields.Method("get_status")

    def get_status(self, obj):
        return obj.calcular_status()


# Nota: como os modelos usam Enum do Python (não string pura), os atributos
# "*_value" acima não existem diretamente no modelo. Preferimos, na prática,
# usar `Model.to_dict()` (já pronto em app/models.py) para a resposta das
# rotas — mais simples e sem duplicar mapeamento. Os schemas Marshmallow
# ficam disponíveis para quem quiser serializar via schema.dump(obj) em
# outros contextos (ex.: exportação, relatórios, integrações).
cidade_schema = CidadeSchema()
cidades_schema = CidadeSchema(many=True)
aviso_schema = AvisoSchema()
avisos_schema = AvisoSchema(many=True)
