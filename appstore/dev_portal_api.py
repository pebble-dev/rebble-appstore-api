from flask import Blueprint, jsonify, abort
from flask_cors import CORS


from .utils import authed_request
from .models import  LockerEntry, UserLike
from .settings import config

parent_app = None
legacy_api = Blueprint('legacy_api', __name__)
CORS(legacy_api)


@legacy_api.route('/me')
def me():
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    rebble_id = me['rebble_id']
    added_ids = [x.id for x in LockerEntry.query.filter_by(user_id=rebble_id)]
    voted_ids = [x.id for x in UserLike.query.filter_by(user_id=rebble_id)]
    return jsonify({
        'users': [{
            'id': me['id'],
            'uid': me['uid'],
        }],
        'added_ids': added_ids,
        'voted_ids': voted_ids,
    })


def init_app(app, url_prefix='/api/v0'):
    global parent_app
    parent_app = app
    app.register_blueprint(legacy_api, url_prefix=url_prefix)
