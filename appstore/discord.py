import json
import requests
import random

from flask import current_app

from .settings import config
from .utils import get_app_description, generate_image_url, who_am_i
import appstore # break the circular dependency to import get_topic_url_for_app from discourse

party_time_emoji = ["🎉","🥳","👏","❤️","🥰","🎊"]

def random_party_emoji():
    return random.choice(party_time_emoji)

def announce_release(app, release, is_generated):

        if config["TEST_APP_UUID"] is not None and config["TEST_APP_UUID"] == str(app.app_uuid):
            return

        release_notes = release.release_notes
        if not release_notes:
            release_notes = "N/A"

        request_fields = [{
            "name": "Release Notes",
            "value": release_notes
        }]

        topic_url = appstore.discourse.get_topic_url_for_app(app)
        if topic_url:
            request_fields.append({
                "name": "Discuss it on the Rebble Dev Forum!",
                "value": topic_url
            })


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
                "fields": request_fields
            }]
        }

        send_discord_webhook(request_data, is_generated)

def announce_new_app(app, is_generated, is_hidden = False):

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

    if is_hidden:
        request_fields.append({
                    "name": "App Visibility",
                    "value": "Unlisted"
        })

    topic_url = appstore.discourse.get_topic_url_for_app(app)
    if topic_url:
        request_fields.append({
            "name": "Discuss it on the Rebble Dev Forum!",
            "value": topic_url
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

    if is_hidden:
        send_admin_discord_webhook(request_data)
    else:
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
            "title": "Wizard Audit Log 🪄",
            "color": int("0xffaa00", 0),
            "description": "Someone has executed a wizard operation on the developer portal",
            "thumbnail": {
                "url": "https://dev-portal.rebble.io/res/img/large_icon_launchpad.svg",
                "height": 80,
                "width": 80
            },
            "fields": request_fields
        }]
    }

    send_admin_discord_webhook(request_data)

def report_app_flag(reported_by, app_name, developer_name, app_id, affected_app_uuid = None):

    if affected_app_uuid is not None:
        if config["TEST_APP_UUID"] is not None and config["TEST_APP_UUID"] == str(affected_app_uuid):
            return

    request_fields = [{
             "name": "App",
             "value": app_name
         },
         {
             "name": "Developer",
             "value": developer_name
         },
         {
             "name": "Reported By",
             "value": "User #" + str(reported_by)
         }
     ]

    request_data = {
        "embeds": [{
            "title": "New Flagged App Report 🚩",
            "color": int("0xFF4745", 0),
            "description": "An end user has reported an app on the appstore from within a mobile app.",
            "thumbnail": {
                "url": "https://i.imgur.com/5f6rGQ9.png",
                "height": 80,
                "width": 80
            },
            "url": f"{config['APPSTORE_ROOT']}/application/{app_id}",
            "fields": request_fields
        }]
    }

    send_admin_discord_webhook(request_data)

def report_app_unlisted(app_name, developer_name, app_id, affected_app_uuid = None):

    if affected_app_uuid is not None:
        if config["TEST_APP_UUID"] is not None and config["TEST_APP_UUID"] == str(affected_app_uuid):
            return

    request_fields = [{
             "name": "App",
             "value": app_name
         },
         {
             "name": "Developer",
             "value": developer_name
         }
     ]

    request_data = {
        "embeds": [{
            "title": "An app was unlisted 👻",
            "color": int("0xFFA845", 0),
            "description": "A developer has unlisted their app from the store.",
            "thumbnail": {
                "url": "https://storage.googleapis.com/rebble-appstore-assets/invisible.png",
                "height": 80,
                "width": 80
            },
            "url": f"{config['APPSTORE_ROOT']}/application/{app_id}",
            "fields": request_fields
        }]
    }

    send_admin_discord_webhook(request_data)

def truncate_string_to_length(string, length):
    if len(string) <= length:
        return string

    return string[:(length - 1)] + '…'

def truncate_data(embed):
    if 'title' in embed:
        embed['title'] = truncate_string_to_length(embed['title'], 256)

    if 'description' in embed:
        embed['description'] = truncate_string_to_length(embed['description'], 4096)

    for field in embed['fields']:
        if 'name' in field:
            field['name'] = truncate_string_to_length(field['name'], 256)

        if 'value' in field:
            field['value'] = truncate_string_to_length(field['value'], 1024)

    if 'author' in embed and 'name' in embed['author']:
        embed['author']['name'] = truncate_string_to_length(embed['author']['name'], 256)

    if 'footer' in embed and 'text' in embed['footer']:
        embed['footer']['text'] = truncate_string_to_length(embed['footer']['text'], 2048)

    return embed

def send_discord_webhook(request_data, is_generated = False):
    request_data['embeds'][0] = truncate_data(request_data['embeds'][0])
    if not is_generated:
        if config['DISCORD_HOOK_URL'] is not None:
            headers = {'Content-Type': 'application/json'}
            r = requests.post(config['DISCORD_HOOK_URL'], data=json.dumps(request_data), headers=headers)
            if r.status_code != 200:
                current_app.logger.warning(f"Discord returned {r.status_code} with message: {r.text}")
    else:
        if config['DISCORD_GENERATED_HOOK_URL'] is not None:
            headers = {'Content-Type': 'application/json'}
            r = requests.post(config['DISCORD_GENERATED_HOOK_URL'], data=json.dumps(request_data), headers=headers)
            if r.status_code != 200:
                current_app.logger.warning(f"Discord returned {r.status_code} with message: {r.text}")

def send_admin_discord_webhook(request_data):
    if config['DISCORD_ADMIN_HOOK_URL'] is not None:
        request_data['embeds'][0] = truncate_data(request_data['embeds'][0])
        headers = {'Content-Type': 'application/json'}
        r = requests.post(config['DISCORD_ADMIN_HOOK_URL'], data=json.dumps(request_data), headers=headers)
        if r.status_code != 200:
            current_app.logger.warning(f"Discord returned {r.status_code} with message: {r.text}")
