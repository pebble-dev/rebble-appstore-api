from algoliasearch import algoliasearch
from flask import Blueprint, jsonify, abort, request
from flask_cors import CORS
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound

from .utils import authed_request, get_uid
from .models import LockerEntry, UserLike, db, App
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
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    if result.status_code != 200:
        abort(401)
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
