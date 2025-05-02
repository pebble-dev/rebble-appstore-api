"""Add apps timeline_token

Revision ID: ec9b0b6d8795
Revises: ddb71f0a1c96
Create Date: 2025-11-08 13:25:52.990174

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'ec9b0b6d8795'
down_revision = 'ddb71f0a1c96'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('apps', sa.Column('timeline_token', sa.String(), nullable=True))


def downgrade():
    op.drop_column('apps', 'timeline_token')
