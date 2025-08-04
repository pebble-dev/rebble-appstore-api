from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm.collections import attribute_mapped_collection

db = SQLAlchemy()
migrate = Migrate()


class Developer(db.Model):
    __tablename__ = "developers"
    id = db.Column(db.String(24), primary_key=True)
    name = db.Column(db.String)
    deploy_key = db.Column(db.String)
    deploy_key_last_used = db.Column(db.DateTime)


class HomeBanners(db.Model):
    __tablename__ = "home_banners"
    id = db.Column(db.Integer, primary_key=True)
    app_type = db.Column(db.String, index=True)
    app_id = db.Column(db.String(24), db.ForeignKey('apps.id'), index=True)
    app = db.relationship('App')



collection_apps = Table('collection_apps', db.Model.metadata,
                        db.Column('collection_id', db.Integer, db.ForeignKey('collections.id', ondelete='cascade')),
                        db.Column('app_id', db.String(24), db.ForeignKey('apps.id', ondelete='cascade')))


class Collection(db.Model):
    __tablename__ = "collections"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String)
    slug = db.Column(db.String, unique=True)
    app_type = db.Column(db.String, index=True)
    platforms = db.Column(ARRAY(db.String))
    apps = db.relationship('App',
                           back_populates='collections',
                           secondary=collection_apps,
                           passive_deletes=True,
                           lazy='dynamic')
db.Index('collection_platforms_index', Collection.platforms, postgresql_using="gin")


class App(db.Model):
    __tablename__ = "apps"
    id = db.Column(db.String(24), primary_key=True)
    app_uuid = db.Column(UUID(), index=True)  # There *are* multiple apps with the same UUID. Good luck!
    asset_collections = db.relationship('AssetCollection',
                                        back_populates='app',
                                        collection_class=attribute_mapped_collection('platform'),
                                        lazy='selectin')
    category_id = db.Column(db.String(24), db.ForeignKey('categories.id'), index=True)
    category = db.relationship('Category', lazy='selectin')
    companions = db.relationship('CompanionApp',
                                 back_populates='app',
                                 collection_class=attribute_mapped_collection('platform'),
                                 lazy='selectin')
    collections = db.relationship('Collection',
                                  back_populates='apps',
                                  secondary=collection_apps,
                                  passive_deletes=True)
    created_at = db.Column(db.DateTime)
    developer_id = db.Column(db.String(24), db.ForeignKey('developers.id'))
    developer = db.relationship('Developer', lazy='joined')
    hearts = db.Column(db.Integer, index=True)
    releases = db.relationship('Release', order_by=lambda: Release.published_date, back_populates='app', lazy='selectin')
    icon_large = db.Column(db.String)
    icon_small = db.Column(db.String)
    published_date = db.Column(db.DateTime)
    source = db.Column(db.String)
    title = db.Column(db.String)
    timeline_enabled = db.Column(db.Boolean)
    type = db.Column(db.String)
    website = db.Column(db.String)
    visible = db.Column(db.Boolean, default=True, server_default='TRUE', nullable=False)


category_banner_apps = Table('category_banner_apps', db.Model.metadata,
                             db.Column('category_id', db.String(24), db.ForeignKey('categories.id', ondelete='cascade')),
                             db.Column('app_id', db.String(24), db.ForeignKey('apps.id', ondelete='cascade')))


class Category(db.Model):
    __tablename__ = "categories"
    id = db.Column(db.String(24), primary_key=True)
    name = db.Column(db.String)
    slug = db.Column(db.String, unique=True)
    colour = db.Column(db.String(6))
    icon = db.Column(db.String)
    app_type = db.Column(db.String, index=True)
    banner_apps = db.relationship('App', secondary=category_banner_apps, passive_deletes=True)
    is_visible = db.Column(db.Boolean)


class CompanionApp(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.String(24), db.ForeignKey('apps.id', ondelete='cascade'), index=True)
    app = db.relationship('App', back_populates='companions')
    icon = db.Column(db.String)
    url = db.Column(db.String)
    platform = db.Column(db.String)
    name = db.Column(db.String)
    pebblekit3 = db.Column(db.Boolean)
db.Index('companion_app_app_platform_index', CompanionApp.app_id, CompanionApp.platform, unique=True)


class AssetCollection(db.Model):
    __tablename__ = "asset_collections"
    id = db.Column(db.Integer, primary_key=True)
    app_id = db.Column(db.String(24), db.ForeignKey('apps.id', ondelete='cascade'))
    platform = db.Column(db.String)
    app = db.relationship('App', back_populates='asset_collections')
    description = db.Column(db.Text)
    screenshots = db.Column(ARRAY(db.String))
    headers = db.Column(ARRAY(db.String))
    banner = db.Column(db.String)
db.Index('asset_collection_app_platform_index', AssetCollection.app_id, AssetCollection.platform, unique=True)


class Release(db.Model):
    __tablename__ = "releases"
    id = db.Column(db.String(24), primary_key=True)
    app_id = db.Column(db.String(24), db.ForeignKey('apps.id', ondelete='cascade'), index=True)
    app = db.relationship('App', back_populates='releases')
    binaries = db.relationship('Binary',
                               back_populates='release',
                               collection_class=attribute_mapped_collection('platform', ignore_unpopulated_attribute=True),
                               lazy='selectin')
    has_pbw = db.Column(db.Boolean())
    capabilities = db.Column(ARRAY(db.String))
    js_md5 = db.Column(db.String(32))
    published_date = db.Column(db.DateTime)
    release_notes = db.Column(db.Text)
    version = db.Column(db.String)
    compatibility = db.Column(ARRAY(db.Text))
    is_published = db.Column(db.Boolean)
db.Index('release_app_compatibility_index', Release.compatibility, postgresql_using="gin")


class Binary(db.Model):
    __tablename__ = "binaries"
    id = db.Column(db.Integer(), primary_key=True)
    release_id = db.Column(db.String(24), db.ForeignKey('releases.id', ondelete='cascade'))
    release = db.relationship('Release', back_populates='binaries')
    platform = db.Column(db.String)
    sdk_major = db.Column(db.Integer)
    sdk_minor = db.Column(db.Integer)
    process_info_flags = db.Column(db.Integer)
    icon_resource_id = db.Column(db.Integer)


class LockerEntry(db.Model):
    __tablename__ = "locker_entries"
    id = db.Column(db.Integer(), primary_key=True)
    app_id = db.Column(db.String(24), db.ForeignKey('apps.id', ondelete='cascade'))
    user_token = db.Column(db.String, index=True)
    app = db.relationship('App')
    user_id = db.Column(db.Integer, index=True)
db.Index('locker_entry_app_user_index', LockerEntry.app_id, LockerEntry.user_id, unique=True)


class UserLike(db.Model):
    __tablename__ = "user_likes"
    user_id = db.Column(db.Integer(), primary_key=True, index=True)
    app_id = db.Column(db.String(24), db.ForeignKey('apps.id', ondelete='cascade'), primary_key=True, index=True)
    app = db.relationship('App')
db.Index('user_like_app_user_index', UserLike.app_id, UserLike.user_id, unique=True)

def init_app(app):
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    migrate.init_app(app, db)
