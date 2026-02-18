from flask import Blueprint, render_template, make_response, url_for
from flask_caching import Cache
from urllib.parse import urljoin
from itertools import product
from copy import deepcopy

from .models import db, App, Collection, Category, Developer
from .settings import config

parent_app = None
api = Blueprint('sitemap', __name__)
cache = Cache()

languages = { 'x-default': '', 'en': 'en_US', 'de': 'de_DE', 'es': 'es_ES', 'fr': 'fr_FR', 'nl': 'nl_NL', 'pl': 'pl_PL', 'zh-Hans': 'zh_CN', 'zh-Hant': 'zh_TW' }
app_types = ['watchapp', 'watchface']
apps_per_page = 100

def process_to_urls(paths):
    urls = []

    for path in paths:
        loc = path['loc']
        path['langs'] = []
        for language in languages:
            path['langs'].append({ 'href': urljoin(config['APPSTORE_ROOT'], f"{languages[language]}/{loc}"), 'code': language })
        for lang in path['langs']:
            localized_path = deepcopy(path)
            localized_path['loc'] = lang['href']
            urls.append(localized_path)

    return urls


@cache.cached(timeout=3600)
@api.route('/sitemap.xml')
def index():
    sitemaps = []

    sitemaps.append(url_for('sitemap.base_routes', _external=True))

    for index in range(int(db.session.query(App.id).filter(App.visible == True).distinct().count() / apps_per_page)):
        sitemaps.append(url_for('sitemap.app_routes', page=index, _external=True))

    resp = make_response(render_template('sitemap_index.xml', sitemaps=sitemaps))
    resp.mimetype = 'application/xml'
    return resp


@cache.cached(timeout=3600)
@api.route('/sitemap-base.xml')
def base_routes():
    paths = []

    for app_type in app_types:
        paths.append({ 'loc': f"{app_type}s", 'priority': 1.0, 'changefreq': 'daily' })
        paths.append({ 'loc': f"search/{app_type}s", 'priority': 0.8 })

    collections = []
    collections.extend(db.session.query(Collection.slug, Collection.app_type).distinct())
    collection_slugs = ['most-loved', 'recently-updated', 'all']
    collections.extend(list(product(collection_slugs, app_types)))
    collections.append(('all-generated', 'watchface')) # Only watchface app_type

    for collection_slug, collection_type in collections:
        paths.append({ 'loc': f"collection/{collection_slug}/{collection_type}s", 'priority': 0.9 })

    for (category_slug,) in db.session.query(Category.slug).filter(Category.is_visible == True).distinct():
        paths.append({ 'loc': f"category/{category_slug}", 'priority': 0.9 })

    resp = make_response(render_template('sitemap_view.xml', urls=process_to_urls(paths)))
    resp.mimetype = 'application/xml'
    return resp

@cache.cached(timeout=3600)
@api.route('/sitemap-apps-<page>.xml')
def app_routes(page):
    paths = []
    page_number = int(page)

    for app_id, recent_hearts, last_modified in db.session.query(App.id, App.recent_hearts, App.updated_at).filter(App.visible == True).distinct().limit(apps_per_page).offset(page_number * apps_per_page):
        if not recent_hearts:
            recent_hearts = 0
        paths.append({ 'loc': f"application/{app_id}", 'priority': min(1.0, recent_hearts), 'lastmod': last_modified })
        paths.append({ 'loc': f"application/{app_id}/changelog", 'lastmod': last_modified })

    resp = make_response(render_template('sitemap_view.xml', urls=process_to_urls(paths)))
    resp.mimetype = 'application/xml'
    return resp

def init_app(app):
    global parent_app
    parent_app = app
    app.register_blueprint(api)
    cache.init_app(app)
