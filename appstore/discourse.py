from pydiscourse.client import DiscourseClient

from .settings import config
from .models import App, db
from .discord import random_party_emoji
from .utils import get_app_description, generate_image_url

PLATFORM_EMOJI = {
    'aplite': ':pebble-orange:',
    'basalt': ':pebble-time-red:',
    'chalk': 'pebble-time-round-14-rainbow',
    'diorite': 'pebble-2-aqua',
    'emery': 'core-time-2-red',
    'flint': 'core-2-duo-black'
}

if config['DISCOURSE_API_KEY'] is None:
    _client = None
else:
    _client = DiscourseClient(host=f"https://{config['DISCOURSE_HOST']}", api_username=config['DISCOURSE_USER'], api_key=config['DISCOURSE_API_KEY'])

def _md_quotify(text):
    return '\n'.join("> " + line for line in text.split('\n'))

def _create_or_post_to_topic(app, is_generated, text):
    if is_generated:
        # For now, we don't post about generated watchfaces.  Maybe they
        # should go in their own topic later?
        return

    if app.discourse_topic_id == -1:
        # We have manually set that we don't want a Discourse topic at all
        # for this app.  Don't post at all.
        return

    if app.discourse_topic_id == 0:
        # This app doesn't have a topic of its own yet; create a new one,
        # and store it in the database.
        
        if app.type == "watchapp":
            tags = ['pebble-app', 'watchapp', app.category.name]
            type_displayed = "Watchapp"
        else:
            tags = ['pebble-app', 'watchface']
            type_displayed = "Watchface"
        
        # If any of this fails, someone can swallow the exception externally.
        rv = _client.create_post(text,
            category_id=config['DISCOURSE_SHOWCASE_TOPIC_ID'],
            title=f"{type_displayed}: {app.title} by {app.developer.name}",
            tags=tags)

        App.query.filter_by(app_uuid=app.app_uuid).update({'discourse_topic_id': rv['topic_id']})
        db.session.commit()
    else:
        _client.create_post(text, category_id=config['DISCOURSE_SHOWCASE_TOPIC_ID'], topic_id=app.discourse_topic_id)

def banner(app):
    asset_collections = app.asset_collections
    for platform in asset_collections:
        banner = asset_collections[platform].banner
        if banner:
            return f"![App banner]({generate_image_url(banner)})"
    return ''

def screenshot_section(app):
    asset_collections = app.asset_collections
    output = ''
    # TODO: Make the order here more intentional
    for index, platform in enumerate(asset_collections):
        if len(asset_collections[platform].screenshots) > 0:
            screenshots = asset_collections[platform].screenshots
            output += f"### {PLATFORM_EMOJI[platform]} {platform.title()} screenshots:\n\n"
            if index != 0:
                output += '[details="Expand"]'
            output += f"|{''.join(['|' for screenshot in screenshots])}\n"
            output += f"|{''.join(['-|' for screenshot in screenshots])}\n"
            screenshot_section = ''.join([f"![Screenshot {s_index}]({generate_image_url(screenshot)})|" for s_index, screenshot in enumerate(screenshots)])
            output += f"|{screenshot_section}\n"
            if index != 0:
                output += '[/details]'
            output += "\n\n"
    return output

def announce_release(app, release, is_generated):
    _create_or_post_to_topic(app, is_generated, text=f"""
# {random_party_emoji()} Update alert!

:party: {app.developer.name} just released *version *{release.version}** of **{app.title}**!

[Go check it out!]({config['APPSTORE_ROOT']}/application/{app.id})

## Release notes

{_md_quotify(release.release_notes or "N/A")}

""")

def announce_new_app(app, is_generated):
    _create_or_post_to_topic(app, is_generated, text=f"""
{banner(app)}

# {app.title} by {app.developer.name}

:party: There's a new {app.type} on the Rebble App Store!

[quote=\"{app.developer.name} says\"]
{get_app_description(app)}
[/quote]

[Go check it out in the App Store!]({config['APPSTORE_ROOT']}/application/{app.id})

{screenshot_section(app)}

###### *P.S.: I'm just a helpful robot that posted this.  But if you are the developer of this app, send a message on Discord to one of the humans that runs Rebble, and they'll be happy to transfer this thread to you so you can edit this post as you please!*
""")

def get_topic_url_for_app(app):
    if not _client or not app.discourse_topic_id or app.discourse_topic_id == -1:
        return None
    return f"https://{config['DISCOURSE_HOST']}/t/{app.discourse_topic_id}"
