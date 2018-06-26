import secrets

from flask import url_for, jsonify, request, abort
from sqlalchemy.orm import joinedload
from sqlalchemy.orm.exc import NoResultFound

from .settings import config
from .models import App, LockerEntry, Release, db
from .api import api
from .utils import get_uid, generate_pbw_url, asset_fallback, generate_image_url, plat_dimensions, jsonify_companion


def jsonify_locker_app(entry):
    app = entry.app
    release = app.releases[-1] if len(app.releases) > 0 else None  # type: Release
    assets = app.asset_collections

    return {
        'id': app.id,
        'uuid': app.app_uuid,
        'user_token': entry.user_token,
        'title': app.title,
        'type': app.type,
        'category': app.category.name,
        'version': release.version if release else None,
        'hearts': app.hearts,
        'is_configurable': 'configurable' in release.capabilities if release and release.capabilities else False,
        'is_timeline_enabled': app.timeline_enabled,
        'links': {
            'remove': url_for('.app_locker', app_uuid=app.app_uuid, _external=True),
            'href': url_for('.app_locker', app_uuid=app.app_uuid, _external=True),
            'share': f"{config['APPSTORE_ROOT']}/applications/{app.id}",
        },
        'developer': {
            'id': app.developer.id,
            'name': app.developer.name,
        },
        'pbw': {
            'file': generate_pbw_url(release.id),
            'icon_resource_id': next(iter(release.binaries.values())).icon_resource_id,
            'release_id': release.id,
        },
        'hardware_platforms': [{
            'sdk_version': f"{x.sdk_major}.{x.sdk_minor}",
            'pebble_process_info_flags': x.process_info_flags,
            'name': x.platform,
            'description': asset_fallback(assets, x.platform).description,
            'images': {
                'icon': generate_image_url(app.icon_small, 48, 48, True),
                'list': generate_image_url(app.icon_large, 144, 144, True),
                'screenshot': generate_image_url(asset_fallback(assets, x.platform).screenshots[0],
                                                 *plat_dimensions[x.platform])
            }
        } for x in release.binaries.values()],
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
                    'supported': x in (release.compatibility if release and release.compatibility else ['aplite', 'basalt', 'diorite', 'emery']),
                    'firmware': {'major': 3}
                } for x in ['aplite', 'basalt', 'chalk', 'diorite', 'emery']
            },
        },
        'companions': {
            'ios': jsonify_companion(app.companions.get('ios')),
            'android': jsonify_companion(app.companions.get('android')),
        },
    }


@api.route("/locker")
def locker():
    uid = get_uid()
    entries = LockerEntry.query.filter_by(user_id=uid).options(joinedload(LockerEntry.app))
    return jsonify({'applications': [jsonify_locker_app(x) for x in entries]})


@api.route("/locker/<app_uuid>", methods=['GET', 'PUT', 'DELETE'])
def app_locker(app_uuid):
    uid = get_uid()
    if request.method == 'GET':
        try:
            entry = LockerEntry.query.join(LockerEntry.app).filter(LockerEntry.user_id == uid,
                                                                   App.app_uuid == app_uuid).one()
        except NoResultFound:
            abort(404)
            return
        return jsonify(jsonify_locker_app(entry))
    elif request.method == 'PUT':
        entry = LockerEntry.query.join(LockerEntry.app).filter(LockerEntry.user_id == uid,
                                                               App.app_uuid == app_uuid).one_or_none()
        if entry is None:
            app = App.query.filter_by(app_uuid=app_uuid).first()
            entry = LockerEntry(app=app, user_id=uid, user_token=secrets.token_urlsafe(32))
            db.session.add(entry)
            db.session.commit()
        return jsonify(application=jsonify_locker_app(entry))
    elif request.method == 'DELETE':
        entry = LockerEntry.query.join(LockerEntry.app).filter(LockerEntry.user_id == uid,
                                                               App.app_uuid == app_uuid).one_or_none()
        if entry:
            db.session.delete(entry)
            db.session.commit()
        return '', 204
