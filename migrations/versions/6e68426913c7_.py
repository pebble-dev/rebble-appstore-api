"""empty message

Revision ID: 6e68426913c7
Revises: 61321bb8e32d
Create Date: 2018-06-26 00:30:06.723815

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6e68426913c7'
down_revision = '61321bb8e32d'
branch_labels = None
depends_on = None


def upgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint('asset_collections_app_id_fkey', 'asset_collections', type_='foreignkey')
    op.create_foreign_key(None, 'asset_collections', 'apps', ['app_id'], ['id'], ondelete='cascade')
    op.drop_constraint('binaries_release_id_fkey', 'binaries', type_='foreignkey')
    op.create_foreign_key(None, 'binaries', 'releases', ['release_id'], ['id'], ondelete='cascade')
    op.drop_constraint('companion_app_app_id_fkey', 'companion_app', type_='foreignkey')
    op.create_foreign_key(None, 'companion_app', 'apps', ['app_id'], ['id'], ondelete='cascade')
    op.drop_constraint('locker_entries_app_id_fkey', 'locker_entries', type_='foreignkey')
    op.create_foreign_key(None, 'locker_entries', 'apps', ['app_id'], ['id'], ondelete='cascade')
    op.drop_constraint('releases_app_id_fkey', 'releases', type_='foreignkey')
    op.create_foreign_key(None, 'releases', 'apps', ['app_id'], ['id'], ondelete='cascade')
    op.drop_constraint('user_likes_app_id_fkey', 'user_likes', type_='foreignkey')
    op.create_foreign_key(None, 'user_likes', 'apps', ['app_id'], ['id'], ondelete='cascade')
    # ### end Alembic commands ###


def downgrade():
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_constraint(None, 'user_likes', type_='foreignkey')
    op.create_foreign_key('user_likes_app_id_fkey', 'user_likes', 'apps', ['app_id'], ['id'])
    op.drop_constraint(None, 'releases', type_='foreignkey')
    op.create_foreign_key('releases_app_id_fkey', 'releases', 'apps', ['app_id'], ['id'])
    op.drop_constraint(None, 'locker_entries', type_='foreignkey')
    op.create_foreign_key('locker_entries_app_id_fkey', 'locker_entries', 'apps', ['app_id'], ['id'])
    op.drop_constraint(None, 'companion_app', type_='foreignkey')
    op.create_foreign_key('companion_app_app_id_fkey', 'companion_app', 'apps', ['app_id'], ['id'])
    op.drop_constraint(None, 'binaries', type_='foreignkey')
    op.create_foreign_key('binaries_release_id_fkey', 'binaries', 'releases', ['release_id'], ['id'])
    op.drop_constraint(None, 'asset_collections', type_='foreignkey')
    op.create_foreign_key('asset_collections_app_id_fkey', 'asset_collections', 'apps', ['app_id'], ['id'])
    # ### end Alembic commands ###