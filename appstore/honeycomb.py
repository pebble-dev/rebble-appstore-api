from flask import request

import beeline
from beeline.patch import requests
from beeline.middleware.flask import HoneyMiddleware
from beeline.trace import _should_sample

from .settings import config

def _sampler(fields):
    sample_rate = 2

    route = fields.get('route') or ''
    if route == 'heartbeat':
        sample_rate = 100
    elif route == 'api.locker':
        sample_rate = 10

    method = fields.get('request.method')
    if method != 'GET':
        sample_rate = 1

    response_code = fields.get('response.status_code')
    if response_code != 200:
        sample_rate = 1
    
    if _should_sample(fields.get('trace.trace_id'), sample_rate):
        return True, sample_rate
    return False, 0

def init_app(app):
    beeline.init(writekey=config['HONEYCOMB_KEY'], dataset='rws', service_name='appstore-api', sampler_hook=_sampler)
    HoneyMiddleware(app, db_events=True)

    @app.before_request
    def before_request():
        beeline.add_context_field("route", request.endpoint)
