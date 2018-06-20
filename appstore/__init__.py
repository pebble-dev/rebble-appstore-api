from flask import Flask

from .settings import config

from .models import init_app as init_models
from .api import init_app as init_api
from .commands import init_app as init_commands

app = Flask(__name__)
app.config.update(**config)
init_models(app)
init_api(app)
init_commands(app)


@app.route('/heartbeat')
def heartbeat():
    return 'ok'
