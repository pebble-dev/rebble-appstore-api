import os
import random
import time
import imghdr
import struct

from typing import Dict, Optional
from uuid import getnode

from PIL import Image

import requests
from flask import request, abort, url_for

import beeline

from .settings import config
from appstore.models import App, AssetCollection, CompanionApp


parent_app = None

class ObjectIdGenerator:
    def __init__(self):
        self.counter = random.randint(0, 0xFFFFFF)
        self.node_id = getnode() % 0xFFFFFF
        self.pid = os.getpid() % 0xFFFF

    def generate(self):
        self.counter = (self.counter + 1) % 0xFFFFFF
        return f'{(int(time.time()) % 0xFFFFFFFF):08x}{self.node_id:06x}{self.pid:04x}{self.counter:06x}'

id_generator = ObjectIdGenerator()

class newAppValidationException(Exception):
    def __init__(self, message="Failed to validate new app", e_code="generic.error"):
        self.message = message
        self.e = e_code
        super().__init__(self.message)

plat_dimensions = {
    'aplite': (144, 168),
    'basalt': (144, 168),
    'chalk': (180, 180),
    'diorite': (144, 168),
    'emery': (200, 228),
}

valid_platforms = [
    "aplite",
    "basalt",
    "chalk",
    "diorite",
    "emery"
]

permitted_image_types = [
    "png",
    "jpeg",
    "gif",
]


def init_app(app):
    global parent_app
    parent_app = app


def _jsonify_common(app: App, target_hw: str) -> dict:
    release = app.releases[-1] if len(app.releases) > 0 else None
    assets = asset_fallback(app.asset_collections, target_hw)

    result = {
        'author': app.developer.name,
        'category_id': app.category_id,
        'category': app.category.name,
        'category_color': app.category.colour,
        'compatibility': {
            'ios': {
                'supported': 'ios' in app.companions or 'android' not in app.companions,
                'min_js_version': 1,
            },
            'android': {
                'supported': 'android' in app.companions or 'ios' not in app.companions,
            },
            **{
                x: {
                    'supported': x in (release.compatibility if release and release.compatibility else ['aplite', 'basalt', 'diorite', 'emery']),
                    'firmware': {'major': 3}
                } for x in ['aplite', 'basalt', 'chalk', 'diorite', 'emery']
            },
        },
        'description': assets.description,
        'developer_id': app.developer_id,
        'hearts': app.hearts,
        'id': app.id,
        'screenshot_hardware': assets.platform,
        'screenshot_images': [{
            'x'.join(str(y) for y in plat_dimensions[assets.platform]): generate_image_url(x, *plat_dimensions[assets.platform], True)
        } for x in assets.screenshots],
        'source': app.source,
        'title': app.title,
        'type': app.type,
        'uuid': app.app_uuid,
        'website': app.website,
        'capabilities': release.capabilities if release else None,
    }
    return result


def jsonify_app(app: App, target_hw: str) -> dict:
    release = app.releases[-1] if len(app.releases) > 0 else None
    assets = asset_fallback(app.asset_collections, target_hw)

    result = _jsonify_common(app, target_hw)

    result = {
        **result,
        'changelog': [{
            'version': x.version,
            'published_date': x.published_date,
            'release_notes': x.release_notes,
        } for x in app.releases],
        'companions': {
            'ios': jsonify_companion(app.companions.get('ios')),
            'android': jsonify_companion(app.companions.get('android')),
        },
        'created_at': app.created_at,
        'header_images': [{
            '720x320': generate_image_url(x, 720, 320),
            'orig': generate_image_url(x),
        } for x in assets.headers] if len(assets.headers) > 0 else '',
        'links': {
            'add_heart': url_for('legacy_api.add_heart', app_id=app.id, _external=True),
            'remove_heart': url_for('legacy_api.remove_heart', app_id=app.id, _external=True),
            'share': f"{config['APPSTORE_ROOT']}/application/{app.id}",
            'add': 'https://a',
            'remove': 'https://b',
            'add_flag': 'https://c',
            'remove_flag': 'https://d',
        },
        'list_image': {
            '80x80': generate_image_url(app.icon_large, 80, 80, True),
            '144x144': generate_image_url(app.icon_large, 144, 144, True),
        },
        'icon_image': {
            '28x28': generate_image_url(app.icon_small, 28, 28, True),
            '48x48': generate_image_url(app.icon_small, 48, 48, True),
        },
        'published_date': app.published_date,
        'visible': app.visible,
    }
    if release:
        result['latest_release'] = {
            'id': release.id,
            'js_md5': release.js_md5,
            'js_version': -1,
            'pbw_file': generate_pbw_url(release.id),
            'published_date': release.published_date,
            'release_notes': release.release_notes,
            'version': release.version,
        }
    return result


def algolia_app(app: App) -> dict:
    assets = asset_fallback(app.asset_collections, 'aplite')
    release = app.releases[-1] if len(app.releases) > 0 else None

    tags = [app.type]
    if release:
        tags.extend(release.compatibility or [])
    else:
        tags.extend(['aplite', 'basalt', 'chalk', 'diorite', 'emery'])
        tags.append('companion-app')
    if len(app.companions) == 0:
        tags.extend(['android', 'ios'])
    else:
        tags.extend(app.companions.keys())

    return {
        **_jsonify_common(app, 'aplite'),
        'asset_collections': [{
            'description': x.description,
            'hardware_platform': x.platform,
            'screenshots': [
                generate_image_url(y, *plat_dimensions[x.platform], True) for y in x.screenshots
            ],
        } for x in app.asset_collections.values()],
        'collections': [x.name for x in app.collections],
        'companions': (str(int('ios' in app.companions)) + str(int('android' in app.companions))),
        **({'ios_companion_url': app.companions['ios'].url} if 'ios' in app.companions else {}),
        **({'android_companion_url': app.companions['android'].url} if 'android' in app.companions else {}),
        'icon_image': generate_image_url(app.icon_small, 48, 48, True),
        'list_image': generate_image_url(app.icon_large, 144, 144, True),
        'js_versions': ['-1', '-1', '-1'],
        'objectID': app.id,
        'screenshot_images': [
            generate_image_url(x, 144, 168, True) for x in assets.screenshots
        ],
        '_tags': tags,
    }


def asset_fallback(collections: Dict[str, AssetCollection], target_hw='basalt') -> AssetCollection:
    # These declare the order we want to try getting a collection in.
    # Note that it is not necessarily the case that we will end up with something that
    # could run on the target device - the aim is to produce some assets at any cost,
    # and given that, produce the sanest possible result.
    # In particular, monochrome devices have colour fallbacks to reduce the chance of
    # ending up with round screenshots.
    fallbacks = {
        'aplite': ['aplite', 'diorite', 'basalt'],
        'basalt': ['basalt', 'aplite'],
        'chalk': ['chalk', 'basalt'],
        'diorite': ['diorite', 'aplite', 'basalt'],
        'emery': ['emery', 'basalt', 'diorite', 'aplite']
    }
    fallback = fallbacks[target_hw]
    for hw in fallback:
        if hw in collections:
            return collections[hw]
    return next(iter(collections.values()))


def generate_image_url(img, width=None, height=None, force=False, freeze=False):
    if img is None:
        return None
    if img == '':
        return ''
    url = parent_app.config['IMAGE_ROOT']
    if width is not None or height is not None:
        if force:
            url += '/exact'
        url += f"/{width or ''}x{height or ''}"
    url += f"/{img}"
    if freeze:
        url += "?freeze=true"
    return url


def generate_pbw_url(release_id: str) -> str:
    return f'{parent_app.config["PBW_ROOT"]}/{release_id}.pbw'


def jsonify_companion(companion: Optional[CompanionApp]) -> Optional[dict]:
    if companion is None:
        return None
    return {
        'id': companion.id,
        'icon': generate_image_url(companion.icon),
        'name': companion.name,
        'url': companion.url,
        'required': True,
        'pebblekit_version': '3' if companion.pebblekit3 else '2',
    }


def get_access_token():
    access_token = request.args.get('access_token')
    if not access_token:
        header = request.headers.get('Authorization')
        if header:
            auth = header.split(' ')
            if len(auth) == 2 and auth[0] == 'Bearer':
                access_token = auth[1]
    if not access_token:
        abort(401)
    beeline.add_context_field('access_token', access_token[-8:])
    return access_token


def authed_request(method, url, **kwargs):
    headers = kwargs.setdefault('headers', {})
    headers['Authorization'] = f'Bearer {get_access_token()}'
    return requests.request(method, url, **kwargs)

def demand_authed_request(method, url, **kwargs):
    result = authed_request(method, url, **kwargs)
    if result.status_code != 200:
        abort(401)
    return result



def get_uid():
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me?flag_authed=true")
    beeline.add_context_field('user', result.json()['uid'])
    return result.json()['uid']

def is_valid_category(category):
    valid_categories = [
        "Daily",
        "Tools & Utilities",
        "Notifications",
        "Remotes",
        "Health & Fitness",
        "Games",
        "Index",
        "Faces",
        "GetSomeApps",
    ]

    return category in valid_categories

def is_valid_platform(platform):
    return platform in valid_platforms

def is_valid_appinfo(appinfo_object):
    # Currently we only need to validate so far as it's ready for the store upload

    basic_required_fields = [
        "uuid",
        "versionLabel",
        "sdkVersion",
        "appKeys",
        "longName",
        "shortName",
        "targetPlatforms",
        "watchapp",
        "resources"
    ]

    appinfo = appinfo_object

    for f in basic_required_fields:
        if not f in appinfo:
            return False, f"Missing field '{f}'"

    for p in appinfo["targetPlatforms"]:
        if not is_valid_platform(p):
            return False, f"Invalid target platform '{p}'"

    return True, ""
    
def validate_new_app_fields(request):
    data = dict(request.form)

    required_fields = [
        "title",
        "type",
        "description",
        "release_notes",
        "category"
    ]

    permitted_sub_types = [
        "watchface",
        "watchapp"
    ]
    
    # First we check we have all the always required fields
    if not all(k in data for k in required_fields):
        raise newAppValidationException("Missing a required field", "field.missing")

    if data["type"] not in permitted_sub_types:
        raise newAppValidationException("Invalid submission type. Expected watchface or watchapp", "subtype.illegal")

    # If we have an app, check app-specific fields
    if data["type"] == "watchapp":
        if not "category" in data:
            raise newAppValidationException("Missing field: category", "category.missing")

        if not is_valid_category(data["category"]):
            raise newAppValidationException("Illegal value for category", "category.illegal")

        if not "small_icon" in request.files:
            raise newAppValidationException("Missing file: small_icon", "small_icon.missing")

        if not "banner" in request.files:
            raise newAppValidationException("Missing file: banner", "banner.missing")

    # Check we have a large icon file
    if not "large_icon" in request.files:
        raise newAppValidationException("Missing file: large_icon", "large_icon.missing")

    if not is_valid_image_file(request.files["large_icon"]):
        raise newAppValidationException("Illegal image type: " + str(imgtype), "large_icon.illegalvalue")

    # Check file types and file sizes of optional images
    if "banner" in request.files:
        if not is_valid_image_file(request.files["banner"]):
            raise newAppValidationException("Illegal image type: " + str(imgtype), "banner.illegalvalue")

        if not is_valid_image_size(request.files["banner"], "banner"):
            max_w, max_h = get_max_image_dimensions("banner")
            raise newAppValidationException(f"Banner has incorrect dimensions. Should be {max_w}x{max_h}", "banner.illegaldimensions")

    if "small_icon" in request.files:
        if not is_valid_image_file(request.files["small_icon"]):
            raise newAppValidationException("Illegal image type: " + str(imgtype), "small_icon.illegalvalue")

        if not is_valid_image_size(request.files["small_icon"], "small_icon"):
            max_w, max_h = get_max_image_dimensions("small_icon")
            raise newAppValidationException(f"Small icon has incorrect dimensions. Should be {max_w}x{max_h}", "small_icon.illegaldimensions")
    

    # Check we have screenshots
    # We must have at least 1 screenshot in total
    # Here we also validate it's an image file and it's the correct dimenisions

    at_least_one_screenshot = False
    for platform in valid_platforms:
        for x in range(1, 6):
             if f"screenshot-{platform}-{x}" in request.files:
                imgtype = imghdr.what(request.files[f"screenshot-{platform}-{x}"])
                if imgtype in permitted_image_types:
                    if is_valid_image_size(request.files[f"screenshot-{platform}-{x}"], f"screenshot_{platform}"):
                        at_least_one_screenshot = True
                    else:
                        max_w, max_h = get_max_image_dimensions(f"screenshot_{platform}")
                        raise newAppValidationException(f"A screenshot has the incorrect dimensions for platform {platform}. Should be {max_w}x{max_h}.", "screenshots.illegaldimensions")
                else:
                    raise newAppValidationException("Illegal image type: " + str(imgtype), "screenshots.illegalvalue")

    if not at_least_one_screenshot:
        raise newAppValidationException("No screenshots provided", "screenshots.noneprovided")

    # Check we have a pbw
    if "pbw" not in request.files:
        raise newAppValidationException("Missing file: pbw", "pbw.missing")

    # If you are here, you are good to go

    return True, "", ""

def clone_asset_collection_without_images(appObject, platform):
    # Find an existing asset collection for AppID and clone the header and desc.
    # Used for uploading new screenshots to a previously nonexisted asset collection.
    # We take an app object as calling func. will have already done a lookup
    for p in valid_platforms:
        og_asset_collection = AssetCollection.query.filter(AssetCollection.app_id == appObject.id, AssetCollection.platform == p).one_or_none()
        if og_asset_collection is not None:
            break

    clone_asset_collection = AssetCollection(
        platform=platform,
        description=og_asset_collection.description,
        screenshots=[],
        headers = og_asset_collection.headers,
        banner = og_asset_collection.banner
    )

    return clone_asset_collection

def is_valid_image_file(file):
    imgtype = imghdr.what(file)
    return imgtype in permitted_image_types

def get_app_description(app):
    for p in valid_platforms:
        if p in app.asset_collections:
            return app.asset_collections[p].description

def is_users_developer_id(developer_id):
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    me = result.json()
    if not me['id'] == developer_id:
        return False
    else:
        return True

def user_is_wizard():
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me")
    me = result.json()
    return me['is_wizard']

def get_image_size(file):
    im = Image.open(file)
    return im.size

def is_valid_image_size(file, image_type):
    
    max_w, max_h = get_max_image_dimensions(image_type)
    image_w, image_h = get_image_size(file)

    if (image_w != max_w) or (image_h != max_h):
        return False
    else:
        return True
    
def get_max_image_dimensions(resource_type):
    max_w = 144
    max_h = 168

    if resource_type == "banner":
        max_w = 720
        max_h = 320
    elif resource_type == "screenshot_chalk":
        max_w = 180
        max_h = 180
    elif resource_type == "screenshot_emery":
        max_w = 200
        max_h = 228
    elif resource_type == "large_icon":
        max_w = 144
        max_h = 144
    elif resource_type == "small_icon":
        max_w = 48
        max_h = 48

    return max_w, max_h

def who_am_i():
    result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me")
    me = result.json()
    return f'{me["name"]} ({me["uid"]})'

def first_version_is_newer(current_release, old_release):
    #1.11 is < 1.1 (mathmatically) so split up by . and check properly
    sections_current = str(current_release).split(".")
    sections_old = str(old_release).split(".")
    for i in range(len(sections_current)):
        try:
            current = int(sections_current[i])
            # Some apps updated manually via Rebble have the "-rbl" suffix, e.g. "1.0-rbl"
            # We have to remove the suffix here otherwise the comparison always fail
            old_numeric_part = sections_old[i].split("-")[0]
            old = int(old_numeric_part)
            if current > old:
                return True
            elif old > current:
                return False
        except IndexError:
            # Current version is longer than old version. I.e. 1.2.1 vs 1.2
            # As long as it's not 0, current is newer
            return current != 0
        except ValueError:
            # The field is a string so it might not be a number
            # In such a case we can't compare so just fail until they change it
            return False
    return False
