from typing import Dict, Optional
import urllib.parse

from flask import Blueprint, request, jsonify, abort, url_for
from flask_cors import CORS

from sqlalchemy.orm.exc import NoResultFound
from .models import App, AssetCollection, Collection, HomeBanners, Category, CompanionApp

api = Blueprint('api', __name__)
CORS(api)


def asset_fallback(collections: Dict[str, AssetCollection], target_hw='basalt') -> AssetCollection:
    # These declare the order we want to try getting a collection in.
    # Note that it is not necessarily the case that we will end up with something that
    # could run on the target device - the aim is to produce some assets at any cost,
    # and given that, produce the sanest possible result.
    # In particular, monochrome devices have colour fallbacks to reduce the chance of
    # ending up with round screenshots.
    fallbacks = {
        'aplite': ['aplite', 'diorite', 'basalt'],
        'basalt': ['basalt', 'aplite'],
        'chalk': ['chalk', 'basalt'],
        'diorite': ['diorite', 'aplite', 'basalt'],
        'emery': ['emery', 'basalt', 'diorite', 'aplite']
    }
    fallback = fallbacks[target_hw]
    for hw in fallback:
        if hw in collections:
            return collections[hw]
    return next(iter(collections.values()))


def generate_pbw_url(release_id: str) -> str:
    return f'https://magic/{release_id}'


def jsonify_companion(companion: Optional[CompanionApp]) -> Optional[dict]:
    if companion is None:
        return None
    return {
        'id': companion.id,
        'icon': companion.icon,
        'name': companion.name,
        'url': companion.url,
        'required': True,
        'pebblekit_version': '3' if companion.pebblekit3 else '2',
    }


def jsonify_app(app: App, target_hw: str) -> dict:
    release = app.releases[0] if len(app.releases) > 0 else None
    assets = asset_fallback(app.asset_collections, target_hw)
    result = {
        'author': app.developer.name,
        'category_id': app.category_id,
        'category': app.category.name,
        'category_color': app.category.colour,
        'changelog': [{
            'version': x.version,
            'published_date': x.published_date,
            'release_notes': x.release_notes,
        } for x in app.releases],
        'companions': {
            'ios': jsonify_companion(app.companions.get('ios')),
            'android': jsonify_companion(app.companions.get('android')),
        },
        'compatibility': {
            'ios': {
                'supported': 'ios' in app.companions or 'android' not in app.companions,
                'min_js_version': 1,
            },
            'android': {
                'supported': 'android' in app.companions or 'ios' not in app.companions,
            },
            **{
                x: {
                    'supported': x in (release.compatibility if release else ['aplite', 'basalt', 'diorite', 'emery']),
                    'firmware': {'major': 3}
                } for x in ['aplite', 'basalt', 'chalk', 'diorite', 'emery']
            },
        },
        'created_at': app.created_at,
        'description': assets.description,
        'developer_id': app.developer_id,
        'header_images': [{'720x320': x, 'orig': x} for x in assets.headers] if len(assets.headers) > 0 else '',
        'hearts': app.hearts,
        'id': app.id,
        #links: todo?
        'list_image': {
            '80x80': app.icon_large,
            '140x140': app.icon_large,
        },
        'icon_image': {
            '28x28': app.icon_small,
            '48x48': app.icon_small,
        },
        'published_date': app.published_date,
        'screenshot_hardware': assets.platform,
        'screenshot_images': [{
            ('144x168' if assets.platform != 'chalk' else '180x180'): x
        } for x in assets.screenshots],
        'source': app.source,
        'title': app.title,
        'type': app.type,
        'uuid': app.app_uuid,
        'website': app.website,
    }
    if release:
        result = {
            **result,
            'latest_release': {
                'id': release.id,
                'js_md5': release.js_md5,
                'js_version': -1,
                'pbw_file': generate_pbw_url(release.id),
                'published_date': release.published_date,
                'release_notes': release.release_notes,
                'version': release.version,
            },
            'capabilities': release.capabilities if release else None,
        }
    return result


def generate_app_response(results):
    target_hw = request.args.get('hardware', 'basalt')
    limit = min(int(request.args.get('limit', '20')), 100)
    offset = int(request.args.get('offset', '0'))
    sorting = request.args.get('sort', 'updated')
    if sorting == 'hearts':
        results = results.order_by(App.hearts.desc())
    else:
        results = results.order_by(App.id.desc())
    # This is slow-ish, but over our appstore size we don't really care.
    paged_results = results.offset(offset).limit(limit + 1)
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


@api.route('/apps/id/<key>')
def apps_by_id(key):
    app = App.query.filter_by(id=key)
    return generate_app_response(app)


@api.route('/apps/dev/<dev>')
def apps_by_dev(dev):
    apps = App.query.filter_by(developer_id=dev)
    return generate_app_response(apps)


@api.route('/apps/category/<category>')
def apps_by_category(category):
    apps = App.query.filter(App.category.has(slug=category))
    return generate_app_response(apps)


@api.route('/apps/collection/<collection>/<app_type>')
def apps_by_collection(collection, app_type):
    type_mapping = {
        'watchapps-and-companions': 'watchapp',
        'apps': 'watchapp',
        'faces': 'watchface',
        'watchfaces': 'watchface'
    }
    if app_type not in type_mapping:
        abort(404)
    app_type = type_mapping[app_type]
    if collection == 'all':
        apps = App.query.filter_by(type=app_type)
    else:
        apps = Collection.query.filter_by(collection).apps.filter_by(type=app_type)
    return generate_app_response(apps)


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

    generated_filter = ((App.app_uuid >= '13371337-0000-0000-0000-000000000000') &
                        (App.app_uuid < '13371338-0000-0000-0000-000000000000'))

    result = {
        'banners': [{
            'application_id': banner.app_id,
            'title': banner.app.title,
            'image': {
                '720x320': asset_fallback(banner.app.asset_collections, hw).banner,
            }
        } for banner in banners],
        'categories': [{
            'id': category.id,
            'name': category.name,
            'slug': category.slug,
            'icon': {
                '88x88': category.icon,
            },
            'color': category.colour,
            'banners': [{
                'application_id': app.id,
                'title': app.title,
                'image': {
                    '720x320': asset_fallback(app.asset_collections, hw).banner
                }
            } for app in category.banner_apps],
            'application_ids': [
                app.id for app in App.query.filter_by(category_id=category.id).limit(20)
            ],
            'links': {
                'apps': url_for('api.apps_by_category', category=category.slug),
            },
        } for category in categories],
        'collections': [*({
            'name': collection.name,
            'slug': collection.slug,
            'application_ids': [x.id for x in collection.apps.limit(20)],
            'links': {
                'apps': url_for('api.apps_by_collection', collection=collection.slug, app_type=home_type)
            },
        } for collection in collections), {
            'name': f'All {"Watchfaces" if app_type == "watchface" else "Watchapps"}',
            'slug': 'all',
            'application_ids': [
                x.id for x in App.query
                    .filter(App.type == app_type, ~generated_filter)
                    .order_by(App.id.desc())
                    .limit(20)],
            'links': {
                'apps': url_for('api.apps_by_collection', collection='all', app_type=home_type),
            }
        }, *([{
            'name': f'Generated Watchfaces',
            'slug': 'all-generated',
            'application_ids': [
                x.id for x in App.query
                    .filter(App.type == app_type, generated_filter)
                    .order_by(App.id.desc())
                    .limit(20)],
            'links': {
                'apps': url_for('api.apps_by_collection', collection='all-generated', app_type=home_type),
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
    app.register_blueprint(api, url_prefix=url_prefix)
