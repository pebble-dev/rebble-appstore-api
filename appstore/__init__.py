from flask import Flask

from .settings import config

from .models import init_app as init_models
from .api import init_app as init_api
from .dev_portal_api import init_app as init_dev_portal_api
from .commands import init_app as init_commands
from .utils import init_app as init_utils

app = Flask(__name__)
app.config.update(**config)
init_models(app)
init_utils(app)
init_api(app)
init_dev_portal_api(app)
init_commands(app)


@app.route('/heartbeat')
def heartbeat():
    return 'ok'
