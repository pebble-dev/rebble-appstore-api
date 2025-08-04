"""Add deploy key col

Revision ID: e56d904098e5
Revises: c4e0470dc040
Create Date: 2025-07-31 23:32:55.499315

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e56d904098e5'
down_revision = 'c4e0470dc040'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('developers', sa.Column('deploy_key', sa.String(), nullable=True))
    op.add_column('developers', sa.Column('deploy_key_last_used', sa.DateTime(), nullable=True))

def downgrade():
    op.drop_column('developers', 'deploy_key')
    # op.drop_column('developers', 'deploy_key_last_used')
