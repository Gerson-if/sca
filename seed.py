"""Popula o banco com dados de exemplo (cidades da região de Aquidauana/MS)
e usuários de teste.

Uso:
    flask seed-db
ou:
    python seed.py   (dentro do app context)
"""
from app import create_app
from app.extensions import db
from app.models import (
    User,
    RoleUsuario,
    StatusUsuario,
    Cidade,
    Aviso,
    PerfilCidade,
    ModoPrazo,
    TipoAberturaFDS,
    ModoDuracaoAviso,
    ConfiguracaoSite,
)


def run_seed():
    # Garante que a configuração da landing page (singleton) já exista.
    ConfiguracaoSite.obter()

    if not User.query.filter_by(username="admin").first():
        admin = User(username="admin", role=RoleUsuario.admin, status=StatusUsuario.aprovado)
        admin.set_password("admin123")  # TROQUE a senha em produção!
        db.session.add(admin)

    # Usuário de exemplo já aprovado, útil para testar a área pública/chat.
    if not User.query.filter_by(username="usuario").first():
        usuario = User(username="usuario", role=RoleUsuario.usuario, status=StatusUsuario.aprovado)
        usuario.set_password("usuario123")
        db.session.add(usuario)

    if Cidade.query.count() == 0:
        db.session.add_all(
            [
                Cidade(
                    nome="Sidrolândia",
                    perfil=PerfilCidade.matriz,
                    modo_prazo=ModoPrazo.periodo,
                    prazo_inicio="2026-07-01",
                    prazo_fim="2026-07-31",
                    regra_horas="24 Horas Operacionais",
                    observacao="Faturamento de contratos nesta filial apenas até o meio-dia.",
                    tecnicos_fim_semana=True,
                    tipo_abertura_fim_semana=TipoAberturaFDS.normal,
                    plantonista_fds="Marcos Silva (Equipe A)",
                    modo_auto_plantonista=False,
                ),
                Cidade(
                    nome="Nioaque",
                    perfil=PerfilCidade.filial,
                    modo_prazo=ModoPrazo.semData,
                    observacao="Feriado municipal no dia 23 com plantão remoto.",
                    tecnicos_fim_semana=False,
                    tipo_abertura_fim_semana=TipoAberturaFDS.emergencia,
                    modo_auto_plantonista=False,
                ),
                Cidade(
                    nome="Jardim",
                    perfil=PerfilCidade.filial,
                    modo_prazo=ModoPrazo.semData,
                    observacao="Cobertura normal, sem restrições no momento.",
                    tecnicos_fim_semana=True,
                    tipo_abertura_fim_semana=TipoAberturaFDS.normal,
                    modo_auto_plantonista=True,
                ),
                Cidade(
                    nome="Aquidauana",
                    perfil=PerfilCidade.filial,
                    modo_prazo=ModoPrazo.dataHora,
                    prazo_inicio="2026-07-10T08:00",
                    prazo_fim="2026-07-20T18:00",
                    regra_horas="Prazo estendido de 48 horas",
                    observacao="Interligação de cabos de fibra na região metropolitana em andamento.",
                    tecnicos_fim_semana=True,
                    tipo_abertura_fim_semana=TipoAberturaFDS.emergencia,
                    modo_auto_plantonista=True,
                ),
                Cidade(
                    nome="Anastácio",
                    perfil=PerfilCidade.filial,
                    modo_prazo=ModoPrazo.semData,
                    observacao="Sem ocorrências registradas.",
                    tecnicos_fim_semana=False,
                    tipo_abertura_fim_semana=TipoAberturaFDS.normal,
                    modo_auto_plantonista=False,
                ),
                Cidade(
                    nome="Bodoquena",
                    perfil=PerfilCidade.filial,
                    modo_prazo=ModoPrazo.semData,
                    observacao="Acesso à zona rural pode sofrer atraso em dias de chuva.",
                    tecnicos_fim_semana=False,
                    tipo_abertura_fim_semana=TipoAberturaFDS.fechado,
                    modo_auto_plantonista=False,
                ),
                Cidade(
                    nome="Guia Lopes da Laguna",
                    perfil=PerfilCidade.filial,
                    modo_prazo=ModoPrazo.periodo,
                    prazo_inicio="2026-07-05",
                    prazo_fim="2026-07-25",
                    regra_horas="Prazo reduzido durante obras na rede",
                    observacao="Manutenção preventiva programada na rede local.",
                    tecnicos_fim_semana=True,
                    tipo_abertura_fim_semana=TipoAberturaFDS.emergencia,
                    modo_auto_plantonista=False,
                ),
            ]
        )

    if Aviso.query.count() == 0:
        db.session.add_all(
            [
                Aviso(
                    titulo="Manutenção programada",
                    descricao="Sistema fora do ar para manutenção de banco de dados por cerca de 2 horas.",
                    modo_duracao=ModoDuracaoAviso.horas,
                    inicio="2026-07-13T22:00",
                    duracao_horas=2,
                ),
                Aviso(
                    titulo="Feriado Municipal Nioaque",
                    descricao="Não haverá suporte operacional presencial na filial Nioaque.",
                    modo_duracao=ModoDuracaoAviso.dias,
                    inicio="2026-07-15",
                    fim="2026-07-15",
                ),
            ]
        )

    db.session.commit()


if __name__ == "__main__":
    app = create_app()
    with app.app_context():
        run_seed()
        print("Seed concluído.")
