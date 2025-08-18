from algoliasearch import algoliasearch
from flask import Blueprint, jsonify, abort, request
from flask_cors import CORS
from werkzeug.exceptions import BadRequest
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from .utils import authed_request, demand_authed_request, get_uid
from .models import LockerEntry, UserLike, db, App, Developer
from .settings import config

parent_app = None
legacy_api = Blueprint('legacy_api', __name__)
CORS(legacy_api)

if config['ALGOLIA_ADMIN_API_KEY']:
    algolia_client = algoliasearch.Client(config['ALGOLIA_APP_ID'], config['ALGOLIA_ADMIN_API_KEY'])
    algolia_index = algolia_client.init_index(config['ALGOLIA_INDEX'])
else:
    algolia_index = None


@legacy_api.route('/users/me')
def me():
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    me = result.json()
    rebble_id = me['rebble_id']
    added_ids = [x.app_id for x in LockerEntry.query.filter_by(user_id=rebble_id)]
    voted_ids = [x.app_id for x in UserLike.query.filter_by(user_id=rebble_id)]
    return jsonify({
        'users': [{
            'id': me['id'],
            'uid': me['uid'],
            'added_ids': added_ids,
            'voted_ids': voted_ids,
            'flagged_ids': [],
            'applications': [],
            'name': me['name'],
            'href': request.url,
        }],
    })


@legacy_api.route('/users/me/developer', methods=['GET'])
def my_apps():
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    me = result.json()

    developer_id = me['id']
    # Get apps
    my_apps = [x for x in App.query.filter_by(developer_id=developer_id)]
    my_appdata = [{"id": a.id, "title": a.title} for a in my_apps]

    # Get developer name
    developer = Developer.query.filter_by(id=developer_id).one_or_none()

    # Check if is wizard (Can we update auth to return this with /me/pebble/appstore?)
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me")
    me_detailed = result.json()
    me["is_wizard"] = me_detailed["is_wizard"]

    if developer is None:
        return jsonify({
            'id': me["id"],
            'userid': me["uid"],
            'href': request.url,
            'authName': me["name"],
            'applications': [],
            'needsSetup': True,
            'w': me["is_wizard"],
        })
    else:
        return jsonify({
                'id': me["id"],
                'userid': me["uid"],
                'href': request.url,
                'authName': me["name"],
                'applications': my_appdata,
                'name': developer.name,
                'needsSetup': False,
                'w': me["is_wizard"],
        })

@legacy_api.route('/users/me/developer', methods=['POST'])
def update_my_developer():
    permitted_fields = ["name"]

    try:
        req = request.json
    except BadRequest as e:
        print(e)
        return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400

    if req is None:
        return jsonify(error="Invalid POST body. Expected JSON and 'Content-Type: application/json'", e="request.invalid"), 400

    for f in req:
        if not f in permitted_fields:
            return jsonify(error=f"Illegal field: {f}", e="illegal.field"), 400

    if not "name" in req:
        return jsonify(error=f"Missing required field: name", e="missing.field.name"), 400

    # Resolve our auth token to our developer ID
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    me = result.json()
    developer_id = me["id"]

    developer = Developer.query.filter_by(id=developer_id).one_or_none()
    if developer is not None:
        print("Update developer from " + developer.name + " to " + req["name"])
        developer.name = req["name"]
        db.session.commit()
        return jsonify(success=True, id=developer.id, name=developer.name)
    else
        return jsonify(success=False, error="You do not have a developer ID to rename. Set up your account first.", e="account.nonexistant"), 400


@legacy_api.route('/applications/<app_id>/add_heart', methods=['POST'])
def add_heart(app_id):
    uid = get_uid()
    try:
        app = App.query.filter_by(id=app_id).one()
        like = UserLike(user_id=uid, app_id=app_id)
        db.session.add(like)
        App.query.filter_by(id=app_id).update({'hearts': App.hearts + 1})
        db.session.commit()
    except NoResultFound:
        abort(404)
        return
    except IntegrityError:
        return "already hearted", 400
    if algolia_index:
        algolia_index.partial_update_object({'objectID': app_id, 'hearts': app.hearts}, no_create=True)
    return 'ok'


@legacy_api.route('/applications/<app_id>/remove_heart', methods=['POST'])
def remove_heart(app_id):
    uid = get_uid()
    try:
        like = UserLike.query.filter_by(app_id=app_id, user_id=uid).one()
    except NoResultFound:
        return ''
    app = like.app
    db.session.delete(like)
    App.query.filter_by(id=app_id).update({'hearts': App.hearts - 1})
    db.session.commit()
    if algolia_index:
        algolia_index.partial_update_object({'objectID': app_id, 'hearts': app.hearts}, no_create=True)
    return 'ok'


def init_app(app, url_prefix='/api/v0'):
    global parent_app
    parent_app = app
    app.register_blueprint(legacy_api, url_prefix=url_prefix)
