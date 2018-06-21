"""empty message

Revision ID: 86ddb5784dde
Revises: ca2ffa55abe6
Create Date: 2018-06-20 11:19:39.212454

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '86ddb5784dde'
down_revision = 'ca2ffa55abe6'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.create_index(op.f('ix_apps_hearts'), 'apps', ['hearts'], unique=False)
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_index(op.f('ix_apps_hearts'), table_name='apps')
    # ### end Alembic commands ###