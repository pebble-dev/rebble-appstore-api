import json
import traceback
import datetime

from algoliasearch import algoliasearch
from flask import Blueprint, jsonify, abort, request
from flask_cors import CORS

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound
from werkzeug.exceptions import BadRequest
from sqlalchemy.exc import DataError
from zipfile import BadZipFile

from .utils import authed_request, get_uid, id_generator, validate_new_app_fields, is_valid_category, is_valid_appinfo, is_valid_platform, clone_asset_collection_without_images, is_valid_image_file, generate_image_url
from .models import Category, db, App, Developer, Release, CompanionApp, Binary, AssetCollection, LockerEntry, UserLike
from .pbw import PBW, release_from_pbw
from .s3 import upload_pbw, upload_asset
from .settings import config
from .discord import announce_release, announce_new_app


parent_app = None
devportal_api = Blueprint('devportal_api', __name__)
CORS(devportal_api)

category_map = {
    'Notifications': '5261a8fb3b773043d5000001',
    'Health & Fitness': '5261a8fb3b773043d5000004',
    'Remotes': '5261a8fb3b773043d5000008',
    'Daily': '5261a8fb3b773043d500000c',
    'Tools & Utilities': '5261a8fb3b773043d500000f',
    'Games': '5261a8fb3b773043d5000012',
    'Index': '527509e36526cda2d4000019',
    'Faces': '528d3ef2dc7b5f580700000a',
    'GetSomeApps': '52ccee3151a80d28e100003e',
}

if config['ALGOLIA_ADMIN_API_KEY']:
    algolia_client = algoliasearch.Client(config['ALGOLIA_APP_ID'], config['ALGOLIA_ADMIN_API_KEY'])
    algolia_index = algolia_client.init_index(config['ALGOLIA_INDEX'])
else:
    algolia_index = None

@devportal_api.route('/onboard', methods=['POST'])
def create_developer():
        try:
           req = request.json
        except BadRequest as e:
            return jsonify(error = "Invalid POST body. Expected JSON", e = "body.invalid"), 400

        if req is None:
            return jsonify(error = "Invalid POST body. Expected JSON", e = "body.invalid"), 400

        result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
        if result.status_code != 200:
            abort(401)
        me = result.json()

        if "name" not in req:
            return jsonify(error = "Missing required field: name", e = "missing.field.name"), 400
        
        try:
            dev = Developer.query.filter_by(id=me['id']).one()
            return jsonify(success = True, message = "User is already on board")
        except NoResultFound:
            dev = Developer(id=me['id'], name=req['name'])
            db.session.add(dev)
            db.session.commit()

        return jsonify(success = True, id = me['id'], message = "Onboarded user")

@devportal_api.route('/submit', methods=['POST'])
def submit_new_app():
        # Validate all fields
        appOK, appError, appErrorCode  = validate_new_app_fields(request)


        if appOK == True:

            params = dict(request.form)

            screenshots = {
                "aplite": [],
                "basalt": [],
                "chalk": [],
                "diorite": []
            }

            try:
                pbw_file = request.files['pbw'].read()
                pbw = PBW(pbw_file, 'aplite')
                with pbw.zip.open('appinfo.json') as f:
                    appinfo = json.load(f)
            except BadZipFile as e:
                return jsonify(error = f"Your pbw file is corrupt or invalid", e = "invalid.pbw"), 400
            except KeyError as e:
                return jsonify(error = f"Your pbw file is invalid or corrupt", e = "invalid.pbw"), 400


            appinfo_valid, appinfo_validation_error = is_valid_appinfo(appinfo)
            if not appinfo_valid:
                return jsonify(error = f"The appinfo.json in your pbw file has the following error: {appinfo_validation_error}", e = "invalid.appinfocontent"), 400
            
            # Check app doesn't already exist
            try:
                if App.query.filter(App.app_uuid == appinfo['uuid']).count() > 0:
                    return jsonify(error = "An app already exists with that UUID", e = "app.exists"), 400
            except DataError as e:
                return jsonify(error = "The UUID provided in appinfo.json is invalid", e = "invalid.uuid"), 400

            # Get developer ID from auth (This is also where we check the user is authenticated)
            result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
            if result.status_code != 200:
                abort(401)
            me = result.json()
            developer_id = me['id']

            # Find developer
            developer = Developer.query.filter(Developer.id == developer_id).one_or_none()

            if developer is None:
                return jsonify(
                    error = "You do not have an active developer account.",
                    e = "account.invalid",
                    message = "Please visit dev-portal.rebble.io to activate your developer account"), 409

            # Upload banner if present
            if "banner" in request.files:
                header_asset = upload_asset(request.files["banner"], request.files["banner"].content_type)
            else:
                header_asset = None

            # Copy screenshots to platform map
            for platform in screenshots:
                for x in range(6):
                    if f"screenshot-{platform}-{x}" in request.files:
                        screenshots[platform].append(request.files[f"screenshot-{platform}-{x}"])

            # Remove any platforms with no screenshots
            screenshots = {k: v for k, v in screenshots.items() if v}

            app_obj = App(
                id = id_generator.generate(),
                app_uuid = appinfo['uuid'],
                asset_collections = {x: AssetCollection(
                    platform=x,
                    description=params['description'],
                    screenshots=[upload_asset(s, s.content_type) for s in screenshots[x]],
                    headers = [header_asset] if header_asset else [],
                    banner = None
                ) for x in screenshots},
                category_id = category_map[params['category']],
                companions = {}, # companions not supported yet
                created_at = datetime.datetime.utcnow(),
                developer = developer,
                hearts = 0,
                releases = [],
                icon_large = upload_asset(request.files['large_icon'], request.files["large_icon"].content_type),
                icon_small = upload_asset(request.files['small_icon'], request.files["small_icon"].content_type) if 'small_icon' in params else '',
                source = params['source'] if 'source' in params else "",
                title = params['title'],
                type = params['type'],
                timeline_enabled = False,
                website = params['website'] if 'source' in params else "",
            )
            db.session.add(app_obj)
            print(f"Created app {app_obj.id}")

            release = release_from_pbw(app_obj, pbw_file,
                                       release_notes = params['release_notes'],
                                       published_date = datetime.datetime.utcnow(),
                                       version = appinfo['versionLabel'],
                                       compatibility = appinfo.get('targetPlatforms', ['aplite', 'basalt', 'diorite', 'emery']))
            print(f"Created release {release.id}")
            upload_pbw(release, request.files['pbw'])
            db.session.commit()

            if algolia_index:
                algolia_index.partial_update_objects([algolia_app(app_obj)], { 'createIfNotExists': True })

            try:
                announce_new_app(app_obj)
            except Exception:
                # We don't want to fail just because Discord is being weird
                print("Discord is being weird")

            return jsonify(success = True, id = app_obj.id)

        else:
            return jsonify(error = appError, e = appErrorCode), 400

@devportal_api.route('/app/<app_id>', methods=['POST'])
def update_app_fields(app_id):
        req = request.json

        if req is None:
            return jsonify(error = "Invalid POST body. Expected JSON", e = "body.invalid"), 400

        allowed_fields_type_map = {
            "title": str,
            "description": str,
            "category": str,
            "website": str,
            "source": str,
            "visible": bool
        }

        # Check all passed fields are allowed
        for x in req:
            if not type(x) == allowed_fields_type_map[x]:
                return jsonify(error = f"Invalid value for field '{x}'", e = f"invalid.field.{x}"), 400


        # Check app exists
        try:
            app = App.query.filter(App.id == app_id).one()
        except NoResultFound:
            return jsonify(error="Unknown app", e="app.notfound"), 400

        # Check we own the app
        result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
        if result.status_code != 200:
            abort(401)
        me = result.json()
        if not me['id'] == app.developer_id:
            return jsonify(error = "You do not have permission to modify that app", e = "permission.denied"), 403

        # Check any enum fields
        if "category" in req and not is_valid_category(req["category"]):
            return jsonify(error = "Invalid value for field: category", e = "invalid.field.category"), 400
        if "visible" in req and not (req["visible"].lower() == "true" or req["visible"].lower() == "false"):
            return jsonify(error = "Invalid value for field: visible", e = "invalid.field.visible"), 400

        # Disallow change face category
        if "category" in req and app.category == "Faces":
            return jsonify(error = "Cannot change category for watchface", e = "disallowed.field.category"), 400

        # Check title length
        if "title" in req and len(req["title"]) > 45:
            return jsonify(error = "Title must be less than 45 characters", e = "invalid.field.title"), 400
            
        # Update the app
        for x in req:
            setattr(app, x, req[x])

        # Updating description requires iterating through asset collection
        if "description" in req:
            for x in app.asset_collections:
                app.asset_collections[x].description = req["description"]

        db.session.commit()
        if algolia_index:
            algolia_index.partial_update_objects([algolia_app(app)], { 'createIfNotExists': False })

        return jsonify(success = True, id = app.id)


@devportal_api.route('/app/<app_id>/release', methods=['POST'])
def submit_new_release(app_id):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound:
        return jsonify(error = "Unknown app", e = "app.notfound"), 400

    # Check we own the app
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    if me['id'] != app.developer_id:
        return jsonify(error = "You do not have permission to modify that app", e = "permission.denied"), 403

    data = dict(request.form)

    if "pbw" not in request.files:
        return jsonify(error = "Missing file: pbw", e = "pbw.missing"), 400

    if "release_notes" not in data:
        return jsonify(error = "Missing field: release_notes", e = "release_notes.missing"), 400

    pbw_file = request.files['pbw'].read()

    try:
        pbw = PBW(pbw_file, 'aplite')
        with pbw.zip.open('appinfo.json') as f:
            appinfo = json.load(f)
    except BadZipFile as e:
        return jsonify(error = f"Your pbw file is invalid or corrupted", e = "invalid.pbw"), 400
    except KeyError as e:
        return jsonify(error = f"Your pbw file is invalid or corrupted", e = "invalid.pbw"), 400

    appinfo_valid, appinfo_valid_reason = is_valid_appinfo(appinfo)
    if not appinfo_valid:
        return jsonify(error = f"The appinfo.json in your pbw file has the following error: {appinfo_valid_reason}", e = "invalid.appinfocontent"), 400

    uuid = appinfo['uuid']
    version = appinfo['versionLabel']
        
    if uuid != app.app_uuid:
        return jsonify(error = "The UUID in appinfo.json does not match the app you are trying to update", e = "uuid.mismatch"), 400

    release_old = Release.query.filter_by(app = app).order_by(Release.published_date.desc()).first()

    if version == release_old.version:
        return jsonify(error = f"The version ({version}) is already on the appstore", e = "version.exists", message = "The app version in appinfo.json is not greater than the latest release on the store. Please increment versionLabel in your appinfo.json and try again."), 400

    release_new = release_from_pbw(app, pbw_file,
                                   release_notes = data["release_notes"],
                                   published_date = datetime.datetime.utcnow(),
                                   version = version,
                                   compatibility = release_old.compatibility)

    upload_pbw(release_new, request.files['pbw'])
    db.session.commit()

    try:
        announce_release(app, release_new)
    except Exception:
        # We don't want to fail just because Discord webhook is being weird
        print("Discord is being weird")

    return jsonify(success = True)
        
# Screenshots 
@devportal_api.route('/app/<app_id>/screenshots')
def missing_platform(app_id):
    return jsonify(error = "Missing platform", e = "platform.missing", message = "Use /app/<id>/screenshots/<platform>"), 400
    
@devportal_api.route('/app/<app_id>/screenshots/<platform>', methods=['GET'])
def get_app_screenshots(app_id, platform):
    # Check app exists

    if not is_valid_platform(platform):
        return jsonify(error = f"Invalid platform: {platform}", e = "platform.invalid"), 400  

    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error = "Unknown app", e = "app.notfound"), 400    

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    if asset_collection is None:
        return jsonify([])
    else:
        return jsonify(asset_collection.screenshots)

@devportal_api.route('/app/<app_id>/screenshots/<platform>', methods=['POST'])
def new_app_screenshots(app_id, platform):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error = "Unknown app", e = "app.notfound"), 400

    # Check we own the app
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    if not me['id'] == app.developer_id:
        return jsonify(error = "You do not have permission to modify that app", e = "permission.denied"), 403

    if not is_valid_platform(platform):
        return jsonify(error = f"Invalid platform: {platform}", e = "platform.invalid"), 400  

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    # Get the first image, this is a single image API
    new_image = next(iter(request.files.to_dict()))
    new_image = request.files[new_image]

    # Check it's a valid image file
    if not is_valid_image_file(new_image):
        return jsonify(error = "Illegal image type", e = "screenshots.illegalvalue"), 400

    if asset_collection is None:
        asset_collection = clone_asset_collection_without_images(app, platform)
        app.asset_collections[platform] = asset_collection
    else:
        # Check we don't already have 5 screenshots in this asset collection
        if len(asset_collection.screenshots) > 4:
            return jsonify(error = "Maximum number of screenshots for platform", e = "screenshot.full", message = "There are already the maximum number of screenshots allowed for this platform. Delete one and try again"), 409

    screenshots = list(asset_collection.screenshots)
    new_image_id = upload_asset(new_image, new_image.content_type)
    screenshots.append(new_image_id)
    asset_collection.screenshots = screenshots
    db.session.commit()

    return jsonify(success = True, id = new_image_id, platform = platform)

@devportal_api.route('/app/<app_id>/screenshots/<platform>/<screenshot_id>', methods=['DELETE'])
def delete_screenshot(app_id, platform, screenshot_id):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error = "Unknown app", e = "app.notfound"), 400

    # Check we own the app
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    if not me['id'] == app.developer_id:
        return jsonify(error = "You do not have permission to modify that app", e = "permission.denied"), 403

    if not is_valid_platform(platform):
        return jsonify(error = f"Invalid platform: {platform}", e = "platform.invalid"), 400  

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    if asset_collection is None:
        return jsonify(error = "Screenshot not found", e = "screenshot.invalid"), 404

    if screenshot_id not in asset_collection.screenshots:
        return jsonify(error = "Screenshot not found", e = "screenshot.invalid"), 404

    if len(asset_collection.screenshots) < 2:
        # Not sure what code to use here. It's not 400 as the request is valid. Don't want a 200. For now returning 409 Conflict
        return jsonify(
            error = "At least one screenshot required per platform", 
            e = "screenshot.islast", 
            message = "Cannot delete the last screenshot as at least one screenshot is required per platform. Add another screenshot then retry the delete operation."
        ), 409

    asset_collection.screenshots = list(filter(lambda x: x != screenshot_id, asset_collection.screenshots))
    db.session.commit()
    return jsonify(success = True, message = f"Deleted screenshot {screenshot_id}", id = screenshot_id, platform = platform)
        
@devportal_api.route('/wizard/rename/<developerID>', methods=['POST'])
def wizard_rename_developer(developerID):
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    if not me['is_wizard']:
        return jsonify(error = "You are not a wizard", e = "permission.denied"), 403

    permitted_fields = ["name"]

    try:
        req = request.json
    except Exception as e:
        print(e)
        return jsonify(error = "Invalid POST body. Expected JSON", e = "body.invalid"), 400

    if req is None:
        return jsonify(error = "Invalid POST body. Expected JSON and 'Content-Type: application/json'", e = "request.invalid"), 400

    for f in req:
        if f not in permitted_fields:
            return jsonify(error = f"Illegal field: {f}", e = "illegal.field"), 400

    if "name" not in req:
        return jsonify(error = f"Missing required field: name", e = "missing.field.name"), 400

    
    developer = Developer.query.filter_by(id=developerID).one_or_none()
    if developer is None:
        return jsonify(error = "Developer not found", e = "id.invalid"), 404
    developer.name = req["name"]
    db.session.commit()

    return jsonify(success = True, id = developer.id, name = developer.name)

@devportal_api.route('/wizard/app/<app_id>', methods=['POST'])
def wizard_update_app(app_id):
    # Update app as a wizard. Currently only allowed field is developer_id 
    allowed_fields = [
        "developer_id"
    ]

    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    if not me['is_wizard']:
        return jsonify(error = "You are not a wizard", e = "permission.denied"), 403

    try:
        req = request.json
    except Exception as e:
        print(e)
        return jsonify(error = "Invalid POST body. Expected JSON", e = "body.invalid"), 400

    if req is None:
        return jsonify(error = "Invalid POST body. Expected JSON", e = "body.invalid"), 400


    for x in req:
        if x not in allowed_fields:
            return jsonify(error = f"Illegal field: {x}", e = "illegal.field"), 400

    app = App.query.filter(App.id == app_id).one_or_none()

    if app is None:
        return jsonify(error = "Unknown app", e = "app.notfound"), 404

    change_occured = False

    if "developer_id" in req:
            app.developer_id = req["developer_id"]
            change_occured = True
    
    if change_occured:
        try:
            db.session.commit()
            return jsonify(success = True, id = app.id, developer_id = app.developer_id)
        except IntegrityError as e:
            return jsonify(error = "Failed to update developer ID. Does new ID exist?", e = "body.invalid"), 400
    else:
        return jsonify(error = "Invalid POST body. Provide one or more fields to update", e = "body.invalid"), 400

    
@devportal_api.route('/wizard/app/<app_id>', methods=['DELETE'])
def wizard_delete_app(app_id):
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    if not me['is_wizard']:
        return jsonify(error = "You are not a wizard", e = "permission.denied"), 403
    
    app = App.query.filter(App.id == app_id).one_or_none()
    if app is None:
        return jsonify(error = "Unknown app", e = "app.notfound"), 404

    App.query.filter(App.id == app_id).delete()

    db.session.commit()

    if algolia_index:
        algolia_index.delete_objects([algolia_app(app)])

    return jsonify(success = True, id = app.id)

@devportal_api.route('/wizard/app/<app_id>', methods=['GET'])
def wizard_get_s3_assets(app_id):
    result = authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me")
    if result.status_code != 200:
        abort(401)
    me = result.json()
    if not me['is_wizard']:
        return jsonify(error = "You are not a wizard", e = "permission.denied"), 403
    
    app = App.query.filter(App.id == app_id).one_or_none()
    if app is None:
        return jsonify(error = "Unknown app", e = "app.notfound"), 404

    images = []
    pbws = []

    if app.icon_large:
        images.append(app.icon_large) 
    if app.icon_small:
        images.append(app.icon_small)

    assets = AssetCollection.query.filter(AssetCollection.app_id == app_id)
    for a in assets:
        images.extend(a.screenshots)
        images.extend(a.headers)

    pbws.extend(r.id for r in Release.query.filter(Release.app_id == app_id))

    print(pbws)

    # Remove duplicates
    images = list(dict.fromkeys(images))
    pbws = list(dict.fromkeys(pbws))

    return jsonify(images = images, pbws = pbws)


def init_app(app, url_prefix='/api/v2'):
    global parent_app
    parent_app = app
    app.register_blueprint(devportal_api, url_prefix=url_prefix)
