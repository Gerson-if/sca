"""configuracao_site: fundo da tela de login (independente da landing page)

Revision ID: 7c2b9f4a1e33
Revises: 20a93fcc58c2
Create Date: 2026-07-20 00:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '7c2b9f4a1e33'
down_revision = '20a93fcc58c2'
branch_labels = None
depends_on = None


def upgrade():
    # Reaproveita o tipo ENUM 'tipofundo' já criado pela migração
    # 36dd6e110058 (create_type=False: não recriar o tipo, só usá-lo em
    # mais uma coluna — a coluna `tipo_fundo` original continua existindo
    # e usando o mesmo tipo).
    tipo_fundo_enum = sa.Enum('nenhum', 'imagem', 'video', name='tipofundo', create_type=False)
    with op.batch_alter_table('configuracao_site', schema=None) as batch_op:
        batch_op.add_column(sa.Column(
            'tipo_fundo_login', tipo_fundo_enum,
            nullable=False, server_default='nenhum',
        ))
        batch_op.add_column(sa.Column('imagem_fundo_login_url', sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column('video_fundo_login_url', sa.String(length=255), nullable=True))
    # server_default só era necessário pra preencher a linha já existente
    # na migração; o modelo (app/models.py) já define o default em Python
    # daqui pra frente, então removemos o default do lado do banco para
    # não divergir do que o SQLAlchemy espera.
    with op.batch_alter_table('configuracao_site', schema=None) as batch_op:
        batch_op.alter_column('tipo_fundo_login', server_default=None)


def downgrade():
    with op.batch_alter_table('configuracao_site', schema=None) as batch_op:
        batch_op.drop_column('video_fundo_login_url')
        batch_op.drop_column('imagem_fundo_login_url')
        batch_op.drop_column('tipo_fundo_login')
    # NÃO derruba o tipo ENUM 'tipofundo' aqui: a coluna `tipo_fundo`
    # (criada em 36dd6e110058) continua usando ele.
