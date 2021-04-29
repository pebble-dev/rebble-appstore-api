import json
import requests
import random

from .settings import config
from .utils import get_app_description
from appstore.models import App

party_time_emoji = ["🎉","🥳","👏","❤️","🥰","🎊"]

def random_party_emoji():
    return random.choice(party_time_emoji)

def announce_release(App, Release):
    try:

        release_notes = Release.release_notes
        if len(release_notes) < 1:
            release_notes = "N/A"

        request_data = {
            "embeds": [{
                "title": f"{str(App.type).capitalize()} Update Alert {random_party_emoji()}",
                "url": f"{config['APPSTORE_ROOT']}/en_US/application/{App.id}",
                "thumbnail": {
                    "url": f"{config['IMAGE_ROOT']}/80x80/filters:upscale()/{App.icon_large}",
                    "height": 80,
                    "width": 80
                },
                "description": f"{App.developer.name} just updated their {App.type} *{App.title}* to version {Release.version}!",
                "fields": [
                    {
                        "name": "Release Notes",
                        "value": release_notes
                    }
                ]
            }]
        }

        send_discord_webhook(request_data)

    except Exception as e:
        # Let's not make a fuss
        return

def announce_new_app(App):
    try:

        request_fields = [
                    {
                        "name": "Name",
                        "value": App.title
                    },
                    {
                        "name": "Description",
                        "value": get_app_description(App)
                    },
                    {
                        "name": "Author",
                        "value": App.developer.name
                    }
        ]

        # Discord gets upset if we send fields with blank values, so we have to add dynamically

        if App.type == "watchapp":
            request_fields.append({
                        "name": "Category",
                        "value": App.category.name
                    })

        if App.source is not None and len(App.source) > 1:
            request_fields.append({
                        "name": "Source URL",
                        "value": App.source
                    })

        if App.website is not None and len(App.website) > 1:
            request_fields.append({
                        "name": "Website",
                        "value": App.website
                    })

        request_data = {
            "embeds": [{
                "title": f"New {str(App.type).capitalize()} Alert {random_party_emoji()}",
                "url": f"{config['APPSTORE_ROOT']}/en_US/application/{App.id}",
                "description": f"There's a new {App.type} on the appstore!",
                "thumbnail": {
                    "url": f"{config['IMAGE_ROOT']}/80x80/filters:upscale()/{App.icon_large}",
                    "height": 80,
                    "width": 80
                },
                "fields": request_fields
            }]
        }

        send_discord_webhook(request_data)

    except Exception as e:
        # Let's not make a fuss
        print(e)
        return


def send_discord_webhook(request_data):
    if config['DISCORD_HOOK_URL'] is not None:
        try:
            headers = {'Content-Type': 'application/json'}
            requests.post(config['DISCORD_HOOK_URL'], data=json.dumps(request_data), headers=headers)
        except Exception as e:
            print(f"Error sending Discord webhook: {e}")
