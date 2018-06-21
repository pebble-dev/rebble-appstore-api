"""empty message

Revision ID: ca2ffa55abe6
Revises: 51a11af8f9ac
Create Date: 2018-06-20 08:55:02.108199

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ca2ffa55abe6'
down_revision = '51a11af8f9ac'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.add_column('binaries', sa.Column('icon_resource_id', sa.Integer(), nullable=True))
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_column('binaries', 'icon_resource_id')
    # ### end Alembic commands ###