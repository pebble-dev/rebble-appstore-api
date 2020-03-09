try:
    import google.auth.exceptions
    try:
        import googleclouddebugger
        googleclouddebugger.enable(module='appstore-api')
    except (ImportError, google.auth.exceptions.DefaultCredentialsError):
        print("Couldn't start cloud debugger")
except ImportError:
    print("Couldn't import google exceptions")

import beeline
from beeline.patch import requests
from beeline.middleware.flask import HoneyMiddleware

from flask import Flask, jsonify, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .settings import config

from .models import init_app as init_models
from .api import init_app as init_api
from .dev_portal_api import init_app as init_dev_portal_api
from .commands import init_app as init_commands
from .utils import init_app as init_utils
from .locker import locker

app = Flask(__name__)
app.config.update(**config)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
if config['HONEYCOMB_KEY']:
     beeline.init(writekey=config['HONEYCOMB_KEY'], dataset='rws', service_name='appstore-api')
     HoneyMiddleware(app, db_events=True)

init_models(app)
init_utils(app)
init_api(app)
init_dev_portal_api(app)
init_commands(app)

@app.before_request
def before_request():
    beeline.add_context_field("route", request.endpoint)

@app.route('/heartbeat')
def heartbeat():
    return 'ok'


@app.route('/dummy', methods=['GET', 'POST'])
def dummy():
    return jsonify({})
