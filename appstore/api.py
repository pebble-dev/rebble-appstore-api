import urllib.parse

from flask import Blueprint, request, jsonify, abort, url_for
from flask_cors import CORS
from sqlalchemy import and_

from sqlalchemy.orm.exc import NoResultFound

from appstore.utils import jsonify_app, asset_fallback, generate_image_url, get_access_token
from .models import App, Collection, HomeBanners, Category, db, Release
from .settings import config

parent_app = None
api = Blueprint('api', __name__)
CORS(api)

HARDWARE_SUPPORT = {
    'aplite': ['aplite'],
    'basalt': ['basalt', 'aplite'],
    'chalk': ['chalk'],
    'diorite': ['diorite', 'aplite'],
    'emery': ['emery', 'diorite', 'basalt', 'aplite'],
    'flint': ['flint', 'diorite', 'aplite']
}


def generate_app_response(results, sort_override=None):
    target_hw = request.args.get('hardware', 'basalt')
    limit = min(int(request.args.get('limit', '20')), 100)
    offset = int(request.args.get('offset', '0'))
    sorting = sort_override or request.args.get('sort', 'updated')
    if sorting == 'hearts':
        results = results.order_by(App.hearts.desc())
    else:
        results = results.order_by(App.id.desc())
    # This is slow-ish, but over our appstore size we don't really care.
    paged_results = results.distinct().offset(offset).limit(limit + 1)
    data = [jsonify_app(x, target_hw) for x in paged_results]
    next_page = None
    if len(data) > limit:
        data.pop()
        args = request.args.to_dict()
        args['offset'] = offset + limit
        args['limit'] = limit
        next_page = f"{request.base_url}?{urllib.parse.urlencode(args)}"

    return jsonify({
        'data': data,
        'limit': limit,
        'offset': offset,
        'links': {
            'nextPage': next_page,
        }
    })


def generated_filter():
    return ((App.app_uuid >= '13371337-0000-0000-0000-000000000000') &
            (App.app_uuid < '13371338-0000-0000-0000-000000000000'))


def hw_compat(hw):
    _compat = (db.session.query(Release.compatibility, Release.app_id)
                        .order_by(Release.published_date.desc())
                        .subquery())
    return and_(_compat.c.compatibility.overlap(HARDWARE_SUPPORT[hw]), _compat.c.app_id == App.id)


def global_filter(hw):
    return and_(hw_compat(hw), App.visible)


@api.route('/apps/id/<key>')
def apps_by_id(key):
    app = App.query.filter_by(id=key)
    return generate_app_response(app)


@api.route('/apps/dev/<dev>')
def apps_by_dev(dev):
    hw = request.args.get('hardware', 'basalt')
    apps = App.query.filter_by(developer_id=dev).filter(global_filter(hw))
    return generate_app_response(apps)


@api.route('/apps/category/<category>')
def apps_by_category(category):
    hw = request.args.get('hardware', 'basalt')
    apps = App.query.filter(App.category.has(slug=category)).filter(global_filter(hw))
    return generate_app_response(apps)


@api.route('/apps/collection/<slug>/<app_type>')
def apps_by_collection(slug, app_type):
    hw = request.args.get('hardware', 'basalt')
    type_mapping = {
        'watchapps-and-companions': 'watchapp',
        'apps': 'watchapp',
        'faces': 'watchface',
        'watchfaces': 'watchface'
    }
    if app_type not in type_mapping:
        abort(404)
    app_type = type_mapping[app_type]
    sort_override = None
    if slug == 'all':
        apps = App.query.filter(App.type == app_type, ~generated_filter(), global_filter(hw))
    elif slug == 'most-loved':
        apps = App.query.filter(App.type == app_type, global_filter(hw))
        sort_override = 'hearts'
    elif slug == 'all-generated':
        apps = App.query.filter(App.type == app_type, generated_filter(), global_filter(hw))
    else:
        collection = Collection.query.filter_by(slug=slug).one_or_none()
        if collection is None:
            abort(404)
        apps = collection.apps.filter_by(type=app_type).filter(global_filter(hw))
    return generate_app_response(apps, sort_override=sort_override)


@api.route('/apps/by_token/<timeline_token>')
def apps_by_token(timeline_token):
    secret = get_access_token()
    if secret != config['SECRET_KEY']:
        abort(401)
    if timeline_token == "":
        abort(404)

    try:
        app = App.query.filter(App.timeline_token == timeline_token).one()
    except NoResultFound:
        abort(404)
        return

    result = {
        "app_uuid": app.app_uuid
    }

    return jsonify(result)


@api.route('/applications/<app_id>/changelog')
def changelogs_by_id(app_id):
    try:
        app = App.query.filter_by(id=app_id).one()
    except NoResultFound:
        abort(404)
        return  # because PyCharm can't tell abort() never returns

    return jsonify({
        'id': app_id,
        'changelog': [{
            'version': x.version,
            'published_date': x.published_date,
            'release_notes': x.release_notes
        } for x in app.releases]
    })

@api.route('/home/<home_type>')
def home(home_type):
    type_mapping = {
        'watchapps-and-companions': 'watchapp',
        'apps': 'watchapp',
        'faces': 'watchface',
        'watchfaces': 'watchface'
    }
    if home_type not in type_mapping:
        abort(404)
    app_type = type_mapping[home_type]

    hw = request.args.get('hardware', 'basalt')

    banners = HomeBanners.query.filter_by(app_type=app_type)

    collections = Collection.query.filter_by(app_type=app_type)
    categories = Category.query.filter_by(app_type=app_type)

    result = {
        'banners': [{
            'application_id': banner.app_id,
            'title': banner.app.title,
            'image': {
                '720x320': generate_image_url(asset_fallback(banner.app.asset_collections, hw).banner, 720, 320),
            }
        } for banner in banners],
        'categories': [{
            'id': category.id,
            'name': category.name,
            'slug': category.slug,
            'icon': {
                '88x88': generate_image_url(category.icon, 88, 88),
            },
            'color': category.colour,
            'banners': [{
                'application_id': app.id,
                'title': app.title,
                'image': {
                    '720x320': generate_image_url(asset_fallback(app.asset_collections, hw).banner, 720, 320),
                }
            } for app in category.banner_apps],
            'application_ids': [],  # It doesn't really care.
            'links': {
                'apps': url_for('api.apps_by_category', category=category.slug),
            },
        } for category in categories],
        'collections': [*({
            'name': collection.name,
            'slug': collection.slug,
            'application_ids': [x.id for x in collection.apps.distinct().limit(7)],
            'links': {
                'apps': url_for('api.apps_by_collection', slug=collection.slug, app_type=home_type)
            },
        } for collection in collections), {
            'name': 'Most Loved',
            'slug': 'most-loved',
            'application_ids': [
                x.id for x in App.query
                    .filter(App.type == app_type, global_filter(hw))
                    .order_by(App.hearts.desc())
                    .distinct()
                    .limit(7)],
            'links': {
                'apps': url_for('api.apps_by_collection', slug='most-loved', app_type=home_type),
            }
        }, {
            'name': f'All {"Watchfaces" if app_type == "watchface" else "Watchapps"}',
            'slug': 'all',
            'application_ids': [
                x.id for x in App.query
                    .filter(App.type == app_type, ~generated_filter(), global_filter(hw))
                    .order_by(App.id.desc())
                    .distinct()
                    .limit(7)],
            'links': {
                'apps': url_for('api.apps_by_collection', slug='all', app_type=home_type),
            }
        }, *([{
            'name': 'Generated Watchfaces',
            'slug': 'all-generated',
            'application_ids': [
                x.id for x in App.query
                    .filter(App.type == app_type, generated_filter(), global_filter(hw))
                    .order_by(App.id.desc())
                    .distinct()
                    .limit(7)],
            'links': {
                'apps': url_for('api.apps_by_collection', slug='all-generated', app_type=home_type),
            }
        }] if app_type == 'watchface' else [])],
    }

    app_ids = set()
    for category in result['categories']:
        app_ids.update(category['application_ids'])
    for collection in result['collections']:
        app_ids.update(collection['application_ids'])

    apps = App.query.filter(App.id.in_(app_ids))
    result['applications'] = [jsonify_app(x, hw) for x in apps]

    return jsonify(result)


def init_app(app, url_prefix='/api/v1'):
    global parent_app
    parent_app = app
    app.register_blueprint(api, url_prefix=url_prefix)
