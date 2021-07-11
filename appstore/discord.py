import json
import requests
import random

from .settings import config
from .utils import get_app_description, generate_image_url
from appstore.models import App

party_time_emoji = ["🎉","🥳","👏","❤️","🥰","🎊"]

def random_party_emoji():
    return random.choice(party_time_emoji)

def announce_release(app, release):
        release_notes = release.release_notes
        if not release_notes:
            release_notes = "N/A"

        request_data = {
            "embeds": [{
                "title": f"{str(app.type).capitalize()} Update Alert {random_party_emoji()}",
                "url": f"{config['APPSTORE_ROOT']}/application/{app.id}",
                "thumbnail": {
                    "url": generate_image_url(app.icon_large, 80, 80),
                    "height": 80,
                    "width": 80
                },
                "description": f"{app.developer.name} just updated their {app.type} *{app.title}* to version {release.version}!",
                "fields": [
                    {
                        "name": "Release Notes",
                        "value": release_notes
                    }
                ]
            }]
        }

        send_discord_webhook(request_data)

def announce_new_app(app):
    request_fields = [{
             "name": "Name",
             "value": app.title
         }, {
             "name": "Description",
             "value": get_app_description(app)
         }, {
             "name": "Author",
             "value": app.developer.name
         }
     ]

    # Discord gets upset if we send fields with blank values, so we have to add dynamically

    if app.type == "watchapp":
        request_fields.append({
                    "name": "Category",
                    "value": app.category.name
                })

    if app.source:
        request_fields.append({
                    "name": "Source URL",
                    "value": app.source
                })

    if app.website:
        request_fields.append({
                    "name": "Website",
                    "value": app.website
                })

    request_data = {
        "embeds": [{
            "title": f"New {str(app.type).capitalize()} Alert {random_party_emoji()}",
            "url": f"{config['APPSTORE_ROOT']}/application/{app.id}",
            "description": f"There's a new {app.type} on the appstore!",
            "thumbnail": {
                "url": generate_image_url(app.icon_large, 80, 80),
                "height": 80,
                "width": 80
            },
            "fields": request_fields
        }]
    }

    send_discord_webhook(request_data)


def send_discord_webhook(request_data):
    if config['DISCORD_HOOK_URL'] is not None:
        headers = {'Content-Type': 'application/json'}
        requests.post(config['DISCORD_HOOK_URL'], data=json.dumps(request_data), headers=headers)
