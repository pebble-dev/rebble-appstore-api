"""Add user_reports table

Revision ID: ddb71f0a1c96
Revises: c4e0470dc040
Create Date: 2025-08-19 23:16:05.018578

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ddb71f0a1c96'
down_revision = 'c4e0470dc040'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'user_flags',
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('app_id', sa.String(length=24), nullable=False),
        sa.PrimaryKeyConstraint('app_id', 'user_id', name='user_flags_pkey')
    )


def downgrade():
    op.drop_table('user_flags')

