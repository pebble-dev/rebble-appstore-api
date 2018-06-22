from flask import Flask

from .settings import config

from .models import init_app as init_models
from .api import init_app as init_api
from .commands import init_app as init_commands
from .utils import init_app as init_utils

import logging
# logging.basicConfig(level=logging.DEBUG)
# logging.getLogger('sqlalchemy.engine').setLevel(logging.INFO)

app = Flask(__name__)
app.config.update(**config)
init_models(app)
init_utils(app)
init_api(app)
init_commands(app)


@app.route('/heartbeat')
def heartbeat():
    return 'ok'
