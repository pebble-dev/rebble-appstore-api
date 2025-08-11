import json
import traceback
import datetime
import uuid

from algoliasearch import algoliasearch
from flask import Blueprint, jsonify, abort, request
from flask_cors import CORS

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
from werkzeug.exceptions import BadRequest
from sqlalchemy.exc import DataError
from zipfile import BadZipFile

from .utils import authed_request, demand_authed_request, get_uid, id_generator, validate_new_app_fields, is_valid_category, is_valid_appinfo, is_valid_platform, clone_asset_collection_without_images, is_valid_image_file, is_valid_image_size, get_max_image_dimensions, generate_image_url, is_users_developer_id, user_is_wizard, newAppValidationException, algolia_app, first_version_is_newer, is_valid_deploy_key_for_app
from .models import Category, db, App, Developer, Release, CompanionApp, Binary, AssetCollection, LockerEntry, UserLike
from .pbw import PBW, release_from_pbw
from .s3 import upload_pbw, upload_asset
from .settings import config
from .discord import announce_release, announce_new_app, audit_log


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
    if config['ALGOLIA_DISABLE']:
        algolia_index = None
    else:
        raise KeyError(f"ALGOLIA_ADMIN_API_KEY not set. Either set key or disable algolia integration with ALGOLIA_DISABLE=True")

@devportal_api.route('/onboard', methods=['POST'])
def create_developer():
        try:
           req = request.json
        except BadRequest as e:
            return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400

        if req is None:
            return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400

        result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
        me = result.json()

        if "name" not in req:
            return jsonify(error="Missing required field: name", e="missing.field.name"), 400
        
        try:
            dev = Developer.query.filter_by(id=me['id']).one()
            return jsonify(success=True, message="User is already on board")
        except NoResultFound:
            dev = Developer(id=me['id'], name=req['name'])
            db.session.add(dev)
            db.session.commit()

        return jsonify(success=True, id=me['id'], message="Onboarded user")

@devportal_api.route('/submit', methods=['POST'])
def submit_new_app():
        # Validate all fields
        try:
            validate_new_app_fields(request)
        except newAppValidationException as validationError:
            return jsonify(error=validationError.message, e=validationError.e), 400


        params = dict(request.form)

        screenshots = {
            "aplite": [],
            "basalt": [],
            "chalk": [],
            "diorite": [],
            "emery": [],
        }

        try:
            pbw_file = request.files['pbw'].read()
            pbw = PBW(pbw_file, 'aplite')
            with pbw.zip.open('appinfo.json') as f:
                appinfo = json.load(f)
        except BadZipFile as e:
            return jsonify(error=f"Your pbw file is corrupt or invalid", e="invalid.pbw"), 400
        except KeyError as e:
            return jsonify(error=f"Your pbw file is invalid or corrupt", e="invalid.pbw"), 400


        appinfo_valid, appinfo_validation_error = is_valid_appinfo(appinfo)
        if not appinfo_valid:
            return jsonify(error=f"The appinfo.json in your pbw file has the following error: {appinfo_validation_error}", e="invalid.appinfocontent"), 400
        
        if params["type"] == "watchface" and not appinfo["watchapp"]["watchface"]:
            return jsonify(error=f"You selected the app type 'Watchface'. This does not match the configuration in your appinfo.json", e="invalid.appinfocontent"), 400
        elif params["type"] == "watchapp" and appinfo["watchapp"]["watchface"]:
            return jsonify(error=f"You selected the app type 'Watch App'. This does not match the configuration in your appinfo.json", e="invalid.appinfocontent"), 400
            
        # Check app doesn't already exist
        try:
            if App.query.filter(App.app_uuid == appinfo['uuid']).count() > 0:
                return jsonify(error="An app already exists with that UUID", e="app.exists"), 400
        except DataError as e:
            return jsonify(error="The UUID provided in appinfo.json is invalid", e="invalid.uuid"), 400

        # Get developer ID from auth (This is also where we check the user is authenticated)
        result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
        me = result.json()
        developer_id = me['id']

        # Find developer
        developer = Developer.query.filter(Developer.id == developer_id).one_or_none()

        if developer is None:
            return jsonify(
                error="You do not have an active developer account.",
                e="account.invalid",
                message="Please visit dev-portal.rebble.io to activate your developer account"), 409

        # Upload banner if present
        if "banner" in request.files:
            header_asset = upload_asset(request.files["banner"], request.files["banner"].content_type)
        else:
            header_asset = None

        # Copy screenshots to platform map
        for platform in screenshots:
            for x in range(1,6):
                if f"screenshot-{platform}-{x}" in request.files:
                    screenshots[platform].append(request.files[f"screenshot-{platform}-{x}"])

        for platform in appinfo["targetPlatforms"]:
            if platform not in screenshots or len(screenshots[platform]) == 0:
                return jsonify(
                    error=f"A screenshot was not provided for supported platform: {platform}",
                    e="screenshot.missing"
                ), 400

        # Remove any platforms with no screenshots
        screenshots = {k: v for k, v in screenshots.items() if v}
        app_obj = App(
            id=id_generator.generate(),
            app_uuid=appinfo['uuid'],
            asset_collections={x: AssetCollection(
                platform=x,
                description=params['description'],
                screenshots=[upload_asset(s, s.content_type) for s in screenshots[x]],
                headers=[header_asset] if header_asset else [],
                banner=None
            ) for x in screenshots},
            category_id=category_map[params['category']],
            companions={}, # companions not supported yet
            created_at=datetime.datetime.utcnow(),
            developer=developer,
            hearts=0,
            releases=[],
            icon_large=upload_asset(request.files['large_icon'], request.files["large_icon"].content_type),
            icon_small=upload_asset(request.files['small_icon'], request.files["small_icon"].content_type) if 'small_icon' in request.files else '',
            source=params['source'] if 'source' in params else "",
            title=params['title'],
            type=params['type'],
            timeline_enabled=False,
            website=params['website'] if 'website' in params else "",
        )
        db.session.add(app_obj)
        print(f"Created app {app_obj.id}")

        release = release_from_pbw(app_obj, pbw_file,
                                   release_notes=params['release_notes'],
                                   published_date=datetime.datetime.utcnow(),
                                   version=appinfo['versionLabel'],
                                   compatibility=appinfo.get('targetPlatforms', ['aplite', 'basalt', 'diorite', 'emery']))
        print(f"Created release {release.id}")
        upload_pbw(release, request.files['pbw'])
        db.session.commit()

        if algolia_index:
            algolia_index.partial_update_objects([algolia_app(app_obj)], { 'createIfNotExists': True })

        try:
            announce_new_app(app_obj, pbw.is_generated())
        except Exception:
            # We don't want to fail just because Discord is being weird
            print("Discord is being weird")

        return jsonify(success=True, id=app_obj.id)


@devportal_api.route('/app/<app_id>', methods=['POST'])
def update_app_fields(app_id):
        req = request.json

        if req is None:
            return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400

        allowed_fields_type_map = {
            "title": str,
            "description": str,
            "category": str,
            "website": str,
            "source": str,
            "visible": bool
        }

        # Check all valid passed fields are correct type
        for x in req:
            if (x in allowed_fields_type_map) and (not type(x) == allowed_fields_type_map[x]):
                return jsonify(error=f"Invalid value for field '{x}'", e=f"invalid.field.{x}"), 400


        # Check app exists
        try:
            app = App.query.filter(App.id == app_id).one()
        except NoResultFound:
            return jsonify(error="Unknown app", e="app.notfound"), 400

        # Check we own the app
        if not is_users_developer_id(app.developer_id):
            return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

        # Check any enum fields
        if "category" in req and not is_valid_category(req["category"]):
            return jsonify(error="Invalid value for field: category", e="invalid.field.category"), 400
        if "visible" in req and not (req["visible"].lower() == "true" or req["visible"].lower() == "false"):
            return jsonify(error="Invalid value for field: visible", e="invalid.field.visible"), 400

        # Disallow change face category
        if "category" in req and app.category == "Faces":
            return jsonify(error="Cannot change category for watchface", e="disallowed.field.category"), 400

        # Check title length
        if "title" in req and len(req["title"]) > 45:
            return jsonify(error="Title must be less than 45 characters", e="invalid.field.title"), 400
            
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

        return jsonify(success=True, id=app.id)


@devportal_api.route('/app/<app_id>/release', methods=['POST'])
def submit_new_release(app_id):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound:
        return jsonify(error="Unknown app", e="app.notfound"), 400

    # Check we own the app
    if not is_users_developer_id(app.developer_id):
        return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

    data = dict(request.form)

    if "pbw" not in request.files:
        return jsonify(error="Missing file: pbw", e="pbw.missing"), 400

    if "release_notes" not in data:
        return jsonify(error="Missing field: release_notes", e="release_notes.missing"), 400

    pbw_file = request.files['pbw'].read()

    try:
        pbw = PBW(pbw_file, 'aplite')
        with pbw.zip.open('appinfo.json') as f:
            appinfo = json.load(f)
    except BadZipFile as e:
        return jsonify(error=f"Your pbw file is invalid or corrupted", e="invalid.pbw"), 400
    except KeyError as e:
        return jsonify(error=f"Your pbw file is invalid or corrupted", e="invalid.pbw"), 400

    appinfo_valid, appinfo_valid_reason = is_valid_appinfo(appinfo)
    if not appinfo_valid:
        return jsonify(error=f"The appinfo.json in your pbw file has the following error: {appinfo_valid_reason}", e="invalid.appinfocontent"), 400

    uuid = appinfo['uuid']
    version = appinfo['versionLabel']

    if str(uuid) != str(app.app_uuid):
        return jsonify(error="The UUID in appinfo.json does not match the app you are trying to update", e="uuid.mismatch"), 400

    release_old = Release.query.filter_by(app=app).order_by(Release.published_date.desc()).first()

    if not first_version_is_newer(version, release_old.version):
        return jsonify(
            error=f"The version ({version}) is already on the appstore", 
            e="version.exists", 
            message="The app version in appinfo.json is not greater than the latest release on the store. Please increment versionLabel in your appinfo.json and try again."
            ), 400

    release_new = release_from_pbw(app, pbw_file,
                                   release_notes=data["release_notes"],
                                   published_date=datetime.datetime.utcnow(),
                                   version=version,
                                   compatibility=appinfo.get('targetPlatforms', ['aplite', 'basalt', 'diorite', 'emery']))

    upload_pbw(release_new, request.files['pbw'])
    db.session.commit()

    try:
        announce_release(app, release_new, pbw.is_generated())
    except Exception:
        # We don't want to fail just because Discord webhook is being weird
        print("Discord is being weird")

    return jsonify(success=True)
        
# Screenshots 
@devportal_api.route('/app/<app_id>/screenshots')
def missing_platform(app_id):
    return jsonify(error="Missing platform", e="platform.missing", message="Use /app/<id>/screenshots/<platform>"), 400
    
@devportal_api.route('/app/<app_id>/screenshots/<platform>', methods=['GET'])
def get_app_screenshots(app_id, platform):
    # Check app exists

    if not is_valid_platform(platform):
        return jsonify(error=f"Invalid platform: {platform}", e="platform.invalid"), 400  

    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 400    

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
        return jsonify(error="Unknown app", e="app.notfound"), 400

    # Check we own the app
    if not is_users_developer_id(app.developer_id):
        return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

    if not is_valid_platform(platform):
        return jsonify(error=f"Invalid platform: {platform}", e="platform.invalid"), 400  

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    # Get the image, this is a single image API
    if "screenshot" in request.files:
        new_image = request.files["screenshot"]
    else:
        return jsonify(error="Missing file: screenshot", e="screenshot.missing"), 400

    # Check it's a valid image file
    if not is_valid_image_file(new_image):
        return jsonify(error="Illegal image type", e="screenshots.illegalvalue"), 400

    # Check it's the correct size
    if not is_valid_image_size(new_image, f"screenshot_{platform}"):
        max_w, max_h = get_max_image_dimensions(f"screenshot_{platform}")
        return jsonify(error="Invalid image size", e="screenshots.illegaldimensions", message=f"Image should be {max_w}x{max_h}"), 400
        
    if asset_collection is None:
        asset_collection = clone_asset_collection_without_images(app, platform)
        app.asset_collections[platform] = asset_collection
    else:
        # Check we don't already have 5 screenshots in this asset collection
        if len(asset_collection.screenshots) > 4:
            return jsonify(error="Maximum number of screenshots for platform", e="screenshot.full", message="There are already the maximum number of screenshots allowed for this platform. Delete one and try again"), 409

    screenshots = list(asset_collection.screenshots)
    new_image_id = upload_asset(new_image, new_image.content_type)
    screenshots.append(new_image_id)
    asset_collection.screenshots = screenshots
    db.session.commit()

    return jsonify(success=True, id=new_image_id, platform=platform)

@devportal_api.route('/app/<app_id>/screenshots/<platform>/<screenshot_id>', methods=['DELETE'])
def delete_screenshot(app_id, platform, screenshot_id):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 400

    # Check we own the app
    if not is_users_developer_id(app.developer_id):
        return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

    if not is_valid_platform(platform):
        return jsonify(error=f"Invalid platform: {platform}", e="platform.invalid"), 400  

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    if asset_collection is None:
        return jsonify(error="Screenshot not found", e="screenshot.invalid"), 404

    if screenshot_id not in asset_collection.screenshots:
        return jsonify(error="Screenshot not found", e="screenshot.invalid"), 404

    if len(asset_collection.screenshots) < 2:
        # Not sure what code to use here. It's not 400 as the request is valid. Don't want a 200. For now returning 409 Conflict
        return jsonify(
            error="At least one screenshot required per platform", 
            e="screenshot.islast", 
            message="Cannot delete the last screenshot as at least one screenshot is required per platform. Add another screenshot then retry the delete operation."
        ), 409

    asset_collection.screenshots = list(filter(lambda x: x != screenshot_id, asset_collection.screenshots))
    db.session.commit()
    return jsonify(success=True, message=f"Deleted screenshot {screenshot_id}", id=screenshot_id, platform=platform)
        
@devportal_api.route('/app/<app_id>/banners/<platform>', methods=['GET'])
def get_app_banners(app_id, platform):
    # Check app exists

    if not is_valid_platform(platform):
        return jsonify(error=f"Invalid platform: {platform}", e="platform.invalid"), 404

    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 404    

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    if asset_collection is None or asset_collection.headers is None:
        return jsonify([])
    else:
        return jsonify(asset_collection.headers)

@devportal_api.route('/app/<app_id>/banners/<platform>', methods=['POST'])
def new_app_banner(app_id, platform):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 404

    # Check we own the app
    if not is_users_developer_id(app.developer_id):
        return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

    if not is_valid_platform(platform):
        return jsonify(error=f"Invalid platform: {platform}", e="platform.invalid"), 404

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    # Get the image, this is a single image API
    if "banner" in request.files:
        new_image = request.files["banner"]
    else:
        return jsonify(error="Missing file: banner", e="banner.missing"), 400

    # Check it's a valid image file
    if not is_valid_image_file(new_image):
        return jsonify(error="Illegal image type", e="banner.illegalvalue"), 400

    # Check it's the correct size
    if not is_valid_image_size(new_image, "banner"):
        max_w, max_h = get_max_image_dimensions("banner")
        return jsonify(error="Invalid image size", e="banner.illegaldimensions", message=f"Image should be {max_w}x{max_h}"), 400
        
    if asset_collection is None:
        # With screenshots we create new asset collection
        # However, if we do that here we can end up with an asset collection for a platform that has no screenshots. So let's fail here and force the user to upload a screenshot for that platform first
        return jsonify(error="You cannot add a banner for a platform which has no screenshots", e="prerequisite.missing", message="Please add at least one screenshot for the selected platform, then retry the banner upload."), 409
    else:
        # Check we don't already have 3 banners in this asset collection
        if len(asset_collection.headers) > 2:
            return jsonify(error="Maximum number of banners for platform", e="banners.full", message="There are already the maximum number of banners allowed for this platform. Delete one and try again"), 409

    headers = list(asset_collection.headers)
    new_image_id = upload_asset(new_image, new_image.content_type)
    headers.append(new_image_id)
    asset_collection.headers = headers
    db.session.commit()

    return jsonify(success=True, id=new_image_id, platform=platform)

@devportal_api.route('/app/<app_id>/banners/<platform>/<banner_id>', methods=['DELETE'])
def delete_banner(app_id, platform, banner_id):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 404

    # Check we own the app
    if not is_users_developer_id(app.developer_id):
        return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

    if not is_valid_platform(platform):
        return jsonify(error=f"Invalid platform: {platform}", e="platform.invalid"), 404

    asset_collection = AssetCollection.query.filter(AssetCollection.app_id == app.id, AssetCollection.platform == platform).one_or_none()

    if asset_collection is None:
        return jsonify(error="Banner not found", e="banner.invalid"), 404

    if banner_id not in asset_collection.headers:
        return jsonify(error="Banner not found", e="banner.invalid"), 404

    if len(asset_collection.headers) < 2 and app.type == "watchapp":
        # Not sure what code to use here. It's not 400 as the request is valid. Don't want a 200. For now returning 409 Conflict
        return jsonify(
            error="At least one header required for watchapps", 
            e="banner.islast", 
            message="Cannot delete the last banner as at least one banner is required for watchapps. Add another banner then delete this one."
        ), 409

    asset_collection.headers = list(filter(lambda x: x != banner_id, asset_collection.headers))
    db.session.commit()
    return jsonify(success=True, message=f"Deleted banner {banner_id}", id=banner_id, platform=platform)
        
@devportal_api.route('/app/<app_id>/icons', methods=['GET'])
def get_app_icons(app_id):
    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 404    

  
    return jsonify(small=app.icon_small, large=app.icon_large)

@devportal_api.route('/app/<app_id>/icon/<size>', methods=['GET'])
def get_app_icon(app_id, size):
    if size not in ("large", "small"):
        return jsonify(error="Invalid icon size. Expected 'small' or 'large'.", e="size.invalid"), 404 

    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 404    

    out = app.icon_small if size == "small" else app.icon_large
    return jsonify(out)

@devportal_api.route('/app/<app_id>/icon/<size>', methods=['POST'])
def new_app_icon(app_id, size):
    if size not in ("large", "small"):
        return jsonify(error="Invalid icon size. Expected 'small' or 'large'.", e="size.invalid"), 404    

    try:
        app = App.query.filter(App.id == app_id).one()
    except NoResultFound as e:
        return jsonify(error="Unknown app", e="app.notfound"), 404

    # Check we own the app
    if not is_users_developer_id(app.developer_id):
        return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

    # Get the image, this is a single image API
    if "icon" in request.files:
        new_image = request.files["icon"]
    else:
        return jsonify(error="Missing file: icon", e="icon.missing"), 400

    # Check it's a valid image file
    if not is_valid_image_file(new_image):
        return jsonify(error="Illegal image type", e="icon.illegalvalue"), 400

    # Check it's the correct size
    if not is_valid_image_size(new_image, f"{size}_icon"):
        max_w, max_h = get_max_image_dimensions(f"{size}_icon")
        return jsonify(error="Invalid image size", e="icon.illegaldimensions", message=f"Image should be {max_w}x{max_h}"), 400
        
    new_image_id = upload_asset(new_image, new_image.content_type)
    if size == "large":
        app.icon_large = new_image_id
    elif size == "small":
        app.icon_small = new_image_id
    db.session.commit()

    return jsonify(success=True, id=new_image_id, size=size)



@devportal_api.route('/wizard/rename/<developer_id>', methods=['POST'])
def wizard_rename_developer(developer_id):
    if not user_is_wizard():
        return jsonify(error="You are not a wizard", e="permission.denied"), 403

    permitted_fields = ["name"]

    try:
        req = request.json
    except BadRequest as e:
        return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400

    if req is None:
        return jsonify(error="Invalid POST body. Expected JSON and 'Content-Type: application/json'", e="request.invalid"), 400

    for f in req:
        if f not in permitted_fields:
            return jsonify(error=f"Illegal field: {f}", e="illegal.field"), 400

    if "name" not in req:
        return jsonify(error=f"Missing required field: name", e="missing.field.name"), 400

    
    developer = Developer.query.filter_by(id=developer_id).one_or_none()
    if developer is None:
        return jsonify(error="Developer not found", e="id.invalid"), 404
    developer.name = req["name"]
    audit_log(f'Renamed developer {developer_id} to {req["name"]}')
    db.session.commit()

    return jsonify(success=True, id=developer.id, name=developer.name)

@devportal_api.route('/wizard/app/<app_id>', methods=['POST'])
def wizard_update_app(app_id):
    # Update app as a wizard. Currently only allowed field is developer_id 
    allowed_fields = [
        "developer_id"
    ]

    if not user_is_wizard():
        return jsonify(error="You are not a wizard", e="permission.denied"), 403

    try:
        req = request.json
    except BadRequest as e:
        return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400

    if req is None:
        return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400


    for x in req:
        if x not in allowed_fields:
            return jsonify(error=f"Illegal field: {x}", e="illegal.field"), 400

    app = App.query.filter(App.id == app_id).one_or_none()

    if app is None:
        return jsonify(error="Unknown app", e="app.notfound"), 404

    change_occured = False

    if "developer_id" in req:
            app.developer_id = req["developer_id"]
            change_occured = True
            audit_log(f'Set developer ID of app \'{app.title}\' ({app.id}) to {req["developer_id"]}')
    
    if change_occured:
        try:
            db.session.commit()
            return jsonify(success=True, id=app.id, developer_id=app.developer_id)
        except IntegrityError as e:
            return jsonify(error="Failed to update developer ID. Does new ID exist?", e="body.invalid"), 400
    else:
        return jsonify(error="Invalid POST body. Provide one or more fields to update", e="body.invalid"), 400


@devportal_api.route('/wizard/app/<app_id>', methods=['DELETE'])
def wizard_delete_app(app_id):
    if not user_is_wizard():
        return jsonify(error="You are not a wizard", e="permission.denied"), 403

    app = App.query.filter(App.id == app_id).one_or_none()
    if app is None:
        return jsonify(error="Unknown app", e="app.notfound"), 404

    if algolia_index:
        algolia_index.delete_objects([app_id])

    App.query.filter(App.id == app_id).delete()

    audit_log(f'Deleted app \'{app.title}\' ({app.id})')

    db.session.commit()

    return jsonify(success=True, id=app_id)

@devportal_api.route('/wizard/app/<app_id>', methods=['GET'])
def wizard_get_s3_assets(app_id):
    if not user_is_wizard():
        return jsonify(error="You are not a wizard", e="permission.denied"), 403
    
    app = App.query.filter(App.id == app_id).one_or_none()
    if app is None:
        return jsonify(error="Unknown app", e="app.notfound"), 404

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

@devportal_api.route("/deploykey", methods=['POST'])
def deploy_key():
    try:
       req = request.json
    except BadRequest as e:
        return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400
    if req is None:
        return jsonify(error="Invalid POST body. Expected JSON", e="body.invalid"), 400

    if not "operation" in req:
        return jsonify(error="Missing required field: operation", e="missing.field.operation"), 400

    if req["operation"] == "regenerate":

        result = demand_authed_request('GET', f"{config['REBBLE_AUTH_URL']}/api/v1/me/pebble/appstore")
        me = result.json()

        try:
            developer = Developer.query.filter_by(id=me['id']).one()
        except NoResultFound:
            return jsonify(error="No developer account associated with user", e="setup.required"), 400

        new_deploy_key = str(uuid.uuid4())
        developer.deploy_key = new_deploy_key
        developer.deploy_key_last_used = None
        db.session.commit()

        return jsonify(new_key=new_deploy_key)

    else:
        return jsonify(error="Unknown operation requested", e="operation.invalid"), 400

@devportal_api.route('/deploy', methods=['POST'])
def submit_new_release_via_deploy():
    # Todo: Merge this with the publish release endpoint

    if not request.headers.get("x-deploy-key"):
        return jsonify(error="No X-Deploy-Key header found", e="permission.denied"), 401

    data = dict(request.form)

    if "pbw" not in request.files:
        return jsonify(error="Missing file: pbw", e="pbw.missing"), 400

    if "release_notes" not in data:
        return jsonify(error="Missing field: release_notes", e="release_notes.missing"), 400

    pbw_file = request.files['pbw'].read()

    try:
        pbw = PBW(pbw_file, 'aplite')
        with pbw.zip.open('appinfo.json') as f:
            appinfo = json.load(f)
    except BadZipFile as e:
        return jsonify(error=f"Your pbw file is invalid or corrupted", e="invalid.pbw"), 400
    except KeyError as e:
        return jsonify(error=f"Your pbw file is invalid or corrupted", e="invalid.pbw"), 400

    appinfo_valid, appinfo_valid_reason = is_valid_appinfo(appinfo)
    if not appinfo_valid:
        return jsonify(error=f"The appinfo.json in your pbw file has the following error: {appinfo_valid_reason}", e="invalid.appinfocontent"), 400

    uuid = appinfo['uuid']
    version = appinfo['versionLabel']

    try:
        app = App.query.filter(App.app_uuid == uuid).one()
    except NoResultFound:
        return jsonify(error="Unknown app. To submit a new app to the appstore for the first time, please use dev-portal.rebble.io", e="app.notfound"), 400
    except MultipleResultsFound:
        return jsonify(error="You cannot use deploy keys with this app. You must submit a release manually through dev-portal.rebble.io", e="app.noteligible"), 400

    # Check we own the app
    if not is_valid_deploy_key_for_app(request.headers.get("x-deploy-key"), app):
        return jsonify(error="You do not have permission to modify that app", e="permission.denied"), 403

    # Update last used time
    dev = Developer.query.filter_by(id=app.developer_id).one()
    dev.deploy_key_last_used = datetime.datetime.now(datetime.timezone.utc)

    release_old = Release.query.filter_by(app=app).order_by(Release.published_date.desc()).first()

    if not first_version_is_newer(version, release_old.version):
        return jsonify(
            error=f"The version ({version}) is already on the appstore",
            e="version.exists",
            message="The app version in appinfo.json is not greater than the latest release on the store. Please increment versionLabel in your appinfo.json and try again."
            ), 400

    release_new = release_from_pbw(app, pbw_file,
                                   release_notes=data["release_notes"],
                                   published_date=datetime.datetime.utcnow(),
                                   version=version,
                                   compatibility=appinfo.get('targetPlatforms', ['aplite', 'basalt', 'diorite', 'emery']))

    upload_pbw(release_new, request.files['pbw'])
    db.session.commit()

    return jsonify(success=True)


def init_app(app, url_prefix='/api/dp'):
    global parent_app
    parent_app = app
    app.register_blueprint(devportal_api, url_prefix=url_prefix)
