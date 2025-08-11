import json
import requests
import random

from .settings import config
from .utils import get_app_description, generate_image_url, who_am_i
from appstore.models import App

party_time_emoji = ["🎉","🥳","👏","❤️","🥰","🎊"]

def random_party_emoji():
    return random.choice(party_time_emoji)

def announce_release(app, release, is_generated):

        if config["TEST_APP_UUID"] is not None and config["TEST_APP_UUID"] == str(app.app_uuid):
            return

        release_notes = release.release_notes
        if not release_notes:
            release_notes = "N/A"

        request_data = {
            "embeds": [{
                "title": f"{str(app.type).capitalize()} Update Alert {random_party_emoji()}",
                "url": f"{config['APPSTORE_ROOT']}/application/{app.id}",
                "thumbnail": {
                    "url": generate_image_url(app.icon_large, 80, 80, True, True),
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

        send_discord_webhook(request_data, is_generated)

def announce_new_app(app, is_generated):

    if config["TEST_APP_UUID"] is not None and config["TEST_APP_UUID"] == str(app.app_uuid):
        return

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

    txt_type = app.type if not is_generated else "Generated Watchface"

    request_data = {
        "embeds": [{
            "title": f"New {str(txt_type).capitalize()} Alert {random_party_emoji()}",
            "url": f"{config['APPSTORE_ROOT']}/application/{app.id}",
            "description": f"There's a new {txt_type} on the appstore!",
            "thumbnail": {
                "url": generate_image_url(app.icon_large, 80, 80, True, True),
                "height": 80,
                "width": 80
            },
            "fields": request_fields
        }]
    }
    
    send_discord_webhook(request_data, is_generated)

def audit_log(operation, affected_app_uuid = None):

    if affected_app_uuid is not None:
        if config["TEST_APP_UUID"] is not None and config["TEST_APP_UUID"] == str(affected_app_uuid):
            return

    request_fields = [{
             "name": "Who?",
             "value": who_am_i()
         }, {
             "name": "What?",
             "value": operation
         }
     ]

    request_data = {
        "embeds": [{
            "title": f"Wizard Audit Log 🪄",
            "color": int("0xffaa00", 0),
            "description": f"Someone has executed a wizard operation on the developer portal",
            "thumbnail": {
                "url": "https://dev-portal.rebble.io/res/img/large_icon_launchpad.svg",
                "height": 80,
                "width": 80
            },
            "fields": request_fields
        }]
    }

    send_admin_discord_webhook(request_data)

def send_discord_webhook(request_data, is_generated = False):
    if not is_generated:
        if config['DISCORD_HOOK_URL'] is not None:
            headers = {'Content-Type': 'application/json'}
            requests.post(config['DISCORD_HOOK_URL'], data=json.dumps(request_data), headers=headers)
    else:
        if config['DISCORD_GENERATED_HOOK_URL'] is not None:
            headers = {'Content-Type': 'application/json'}
            requests.post(config['DISCORD_GENERATED_HOOK_URL'], data=json.dumps(request_data), headers=headers)            

def send_admin_discord_webhook(request_data):
    if config['DISCORD_ADMIN_HOOK_URL'] is not None:
        headers = {'Content-Type': 'application/json'}
        requests.post(config['DISCORD_ADMIN_HOOK_URL'], data=json.dumps(request_data), headers=headers)
