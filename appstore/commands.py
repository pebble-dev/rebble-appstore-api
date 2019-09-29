import datetime
import hashlib
import json
import yaml

import flask.json
import shutil
import subprocess
import uuid
import zipfile

import click
import os
from flask.cli import AppGroup

import requests
from sqlalchemy.orm import load_only
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.exc import IntegrityError

from algoliasearch import algoliasearch

from .utils import id_generator, algolia_app
from .models import Category, db, App, Developer, Release, CompanionApp, Binary, AssetCollection, LockerEntry, UserLike
from .pbw import PBW, release_from_pbw
from .s3 import upload_pbw, upload_asset
from .settings import config

if config['ALGOLIA_ADMIN_API_KEY']:
    algolia_client = algoliasearch.Client(config['ALGOLIA_APP_ID'], config['ALGOLIA_ADMIN_API_KEY'])
    algolia_index = algolia_client.init_index(config['ALGOLIA_INDEX'])
else:
    algolia_index = None

apps = AppGroup('apps')

@apps.command('import-home')
@click.argument('home_type')
def import_categories(home_type):
    result = requests.get(f'https://api2.getpebble.com/v2/home/{home_type}')
    categories = result.json()['categories']
    for category in categories:
        obj = Category(id=category['id'], name=category['name'], slug=category['slug'],
                       icon=category.get('icon', {}).get('88x88', None), colour=category['color'], banner_apps=[],
                       is_visible=True, app_type='watchface' if home_type == 'faces' else 'watchapp')
        db.session.add(obj)
        print(f"Added category: {obj.name} ({obj.id})")
    db.session.commit()


def fetch_apps(url):
    while url is not None:
        print(f"Fetching {url}...")
        content = requests.get(url).json()
        for app in content['data']:
            yield app
        url = content.get('links', {}).get('nextPage', None)


def parse_datetime(string: str) -> datetime.datetime:
    t = datetime.datetime.strptime(string.split('.', 1)[0], '%Y-%m-%dT%H:%M:%S')
    t = t.replace(tzinfo=datetime.timezone.utc)
    return t


def fetch_file(url, destination):
    if os.path.exists(destination):
        return
    subprocess.check_call(["wget", url, "-O", destination])


@apps.command('fix-capabilities')
def fix_caps():
    for pbw_path in os.listdir('pbws'):
        release_id = pbw_path[:-4]
        try:
            pbw = PBW(f'pbws/{pbw_path}', 'aplite')
            caps = [x for x in pbw.get_capabilities() if x != '']
        except (KeyError, zipfile.BadZipFile):
            print("Invalid PBW!?")
            continue
        try:
            release = Release.query.filter_by(id=release_id).one()
        except NoResultFound:
            print("PBW with no release: {release_id}")
            continue
        print(f"{release.id}: {release.capabilities} -> {caps}")
        release.capabilities = caps
    db.session.commit()


@apps.command('import-apps')
@click.argument('app_type')
def import_apps(app_type):
    for app in fetch_apps(f"https://api2.getpebble.com/v2/apps/collection/all/{app_type}?hardware=basalt&filter_hardware=false&limit=100"):
        try:
            dev = Developer.query.filter_by(id=app['developer_id']).one()
        except NoResultFound:
            dev = Developer(id=app['developer_id'], name=app['author'])
            db.session.add(dev)
        if App.query.filter_by(id=app['id']).count() > 0:
            continue
        print(f"Adding app: {app['title']} ({app.get('uuid')}, {app['id']})...")

        release = app.get('latest_release')
        if release:
            filename = f"pbws/{release['id']}.pbw"
            if not os.path.exists(filename):
                try:
                    fetch_file(release['pbw_file'], filename)
                except subprocess.CalledProcessError:
                    print("Failed to grab pbw.")
                    continue
            try:
                PBW(filename, 'aplite')
            except zipfile.BadZipFile:
                print("Bad PBW!")
                os.unlink(filename)
                continue
        else:
            filename = None

        app_obj = App(
            id=app['id'],
            app_uuid=app.get('uuid'),
            category_id=app['category_id'],
            companions={
                k: CompanionApp(
                    icon=fix_image_url(v['icon']),
                    name=v['name'],
                    url=v['url'],
                    platform=k,
                    pebblekit3=(v['pebblekit_version'] == '3'),
                ) for k, v in app['companions'].items() if v is not None
            },
            created_at=parse_datetime(app['created_at']),
            developer=dev,
            hearts=app['hearts'],
            releases=[
                *([Release(
                    id=release['id'],
                    js_md5=release.get('js_md5', None),
                    has_pbw=True,
                    capabilities=app['capabilities'] or [],
                    published_date=parse_datetime(release['published_date']),
                    release_notes=release['release_notes'],
                    version=release.get('version'),
                    compatibility=[
                        k for k, v in app['compatibility'].items() if v['supported'] and k not in ('android', 'ios')
                    ],
                    is_published=True,
                )] if release else []), *[Release(
                        id=id_generator.generate(),
                        has_pbw=False,
                        published_date=parse_datetime(log['published_date']),
                        version=log.get('version', ''),
                        release_notes=log['release_notes']
                ) for log in app['changelog'] if log.get('version', '') != release.get('version', '')]
            ],
            icon_large=fix_image_url((app.get('list_image') or {}).get('144x144') or ''),
            icon_small=fix_image_url((app.get('icon_image') or {}).get('48x48') or ''),
            published_date=app.get('published_date', release['published_date'] if release else None),
            source=app['source'] or None,
            title=app['title'],
            type=app['type'],
            website=app['website'] or None,
        )
        db.session.add(app_obj)

        done = set()
        for platform in (app_obj.releases[0].compatibility
                         if len(app_obj.releases) > 0
                         else ['aplite', 'basalt', 'chalk', 'diorite', 'emery']):
            r = requests.get(f"https://api2.getpebble.com/v2/apps/id/{app_obj.id}?hardware={platform}")
            r.raise_for_status()
            data = r.json()['data'][0]
            if data['screenshot_hardware'] not in done:
                done.add(data['screenshot_hardware'])
            else:
                continue
            collection = AssetCollection(app=app_obj, platform=data['screenshot_hardware'],
                                         description=data.get('description', ''),
                                         screenshots=[fix_image_url(next(iter(x.values()))) for x in data['screenshot_images']],
                                         headers=[fix_image_url(next(iter(x.values()))) for x in data['header_images']] if data.get('header_images') else [],
                                         banner=None)
            db.session.add(collection)

        if filename:
            for platform in ['aplite', 'basalt', 'chalk', 'diorite', 'emery']:
                pbw = PBW(filename, platform)
                if not pbw.has_platform:
                    continue
                metadata = pbw.get_app_metadata()
                binary = Binary(release_id=release['id'], platform=platform,
                                sdk_major=metadata['sdk_version_major'], sdk_minor=metadata['sdk_version_minor'],
                                process_info_flags=metadata['flags'], icon_resource_id=metadata['icon_resource_id'])
                db.session.add(binary)
        db.session.commit()


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


mimetype_map = {
    'image/png': 'png',
    'image/jpeg': 'jpg',
    'image/gif': 'gif',
}


def fix_image_url(url):
    if url == '':
        return ''
    identifier = url.split('/file/')[1].split('/convert')[0]
    s = requests.get(url, stream=True)
    # content_type = s.headers['Content-Type']
    # if content_type not in mimetype_map:
    #     print(f"Skipping unknown content-type {content_type}.")
    #     return None
    with open(f'images/{identifier}', 'wb') as f:
        shutil.copyfileobj(s.raw, f)
    return identifier


def import_app_from_locker(locker_app):
    print(f"Adding missing app {locker_app['title']}...")
    if locker_app['developer']['id'] is None:
        locker_app['developer']['id'] = id_generator.generate()
    try:
        dev = Developer.query.filter_by(id=locker_app['developer']['id']).one()
    except NoResultFound:
        dev = Developer(id=locker_app['developer']['id'], name=locker_app['developer']['name'])
        db.session.add(dev)

    release = locker_app.get('pbw')
    if release:
        filename = f"pbws/{release['release_id']}.pbw"
        if not os.path.exists(filename):
            with requests.get(release['file'], stream=True) as r:
                if r.status_code != 200:
                    print(f"FAILED to download pbw.")
                    return False
                with open(filename, 'wb') as f:
                    shutil.copyfileobj(r.raw, f)
        try:
            if PBW(filename, 'aplite').zip.testzip() is not None:
                raise zipfile.BadZipFile
        except zipfile.BadZipFile:
            print("Bad PBW!")
            os.unlink(filename)
            return False
    else:
        filename = None

    created_at = datetime.datetime.utcfromtimestamp(int(locker_app['id'][:8], 16)).replace(tzinfo=datetime.timezone.utc)

    portal_info = requests.get(f"https://dev-portal.getpebble.com/api/applications/{locker_app['id']}")
    if portal_info.status_code != 200:
        print("Couldn't get dev portal info for app; skipping.")
        return None
    portal_info = portal_info.json()['applications'][0]

    app = App(
        id=locker_app['id'],
        app_uuid=locker_app['uuid'],
        asset_collections={x['name']: AssetCollection(
            platform=x['name'],
            description=x.get('description'),
            screenshots=[fix_image_url(x['images']['screenshot'])],
            headers=[],
            banner=None
        ) for x in locker_app['hardware_platforms']},
        category_id=category_map.get(locker_app['category'], None),
        companions={
            k: CompanionApp(
                icon=v['icon'],
                name=v['name'],
                url=v['url'],
                platform=k,
                pebblekit3=(v['pebblekit_version'] == '3'),
            ) for k, v in locker_app['companions'].items() if v is not None
        },
        collections=[],
        created_at=created_at,
        developer=dev,
        hearts=locker_app['hearts'],
        icon_small=fix_image_url(portal_info['icon_image']),
        icon_large=fix_image_url(portal_info['list_image']),
        published_date=created_at,
        releases=[],
        source=None,
        title=locker_app['title'],
        type=locker_app['type'],
        website=None,
        visible=False,
    )
    db.session.add(app)

    if filename:
        pbw = PBW(filename, 'aplite')
        js_md5 = None
        if pbw.has_javascript:
            with pbw.zip.open('pebble-js-app.js', 'r') as f:
                js_md5 = hashlib.md5(f.read()).hexdigest()
        release_obj = Release(
            id=release['release_id'],
            app_id=locker_app['id'],
            has_pbw=True,
            capabilities=pbw.get_capabilities(),
            js_md5=js_md5,
            published_date=created_at,
            release_notes=None,
            compatibility=[k for k, v in locker_app['compatibility'].items() if v['supported'] and k not in ('android', 'ios')],
            is_published=True,
        )
        db.session.add(release_obj)
        for platform in ['aplite', 'basalt', 'chalk', 'diorite', 'emery']:
            pbw = PBW(filename, platform)
            if not pbw.has_platform:
                continue
            metadata = pbw.get_app_metadata()
            binary = Binary(release=release_obj, platform=platform,
                            sdk_major=metadata['sdk_version_major'], sdk_minor=metadata['sdk_version_minor'],
                            process_info_flags=metadata['flags'], icon_resource_id=metadata['icon_resource_id'])
            db.session.add(binary)
    db.session.commit()
    return app


@apps.command('import-lockers')
def import_lockers():
    with open('users.txt') as f:
        processed = set()
        missing = set()
        for entry in f:
            uid, token = entry.strip().split()
            uid = int(uid)
            print(f"user {uid}...")
            url = "https://appstore-api.getpebble.com/v2/locker"
            entries = []
            total_entries = 0
            while url is not None:
                result = requests.get(url, headers={'Authorization': f"Bearer {token}"})
                if result.status_code != 200:
                    print(f"Skipping bad user: {uid}")
                app_ids = [x['id'] for x in result.json()['applications']]
                existing = {x.id: x for x in App.query.filter(App.id.in_(app_ids))}
                total_entries += len(app_ids)
                for app in result.json()['applications']:
                    if app['id'] not in existing:
                        if app['id'] not in missing:
                            added = import_app_from_locker(app)
                            if added is None:
                                missing.add(app['id'])
                        else:
                            added = None
                        if not added:
                            print("Skipping bad app...")
                            continue
                        else:
                            existing[added.id] = added
                    if app['id'] not in processed:
                        existing[app['id']].timeline_enabled = app['is_timeline_enabled']
                        processed.add(app['id'])

                    entries.append(LockerEntry(app_id=app['id'], user_token=app.get('user_token'), user_id=uid))
                url = result.json()['nextPageURL']
            db.session.add_all(entries)
            db.session.commit()
            print(f"Added {len(existing)} of {total_entries} apps.")
    print("done.")


@apps.command('import-likes')
def import_likes():
    known_apps = set(x.id for x in App.query.options(load_only('id')))
    with open('users.txt') as f:
        for entry in f:
            uid, token = entry.strip().split()
            uid = int(uid)
            print(f"Importing user {uid}...")
            dev_portal = requests.get('https://dev-portal.getpebble.com/api/users/me',
                                      headers={'Authorization': f"Bearer {token}"})
            if dev_portal.status_code != 200:
                print(f"Skipping user {uid}: dev portal didn't load: {dev_portal.status_code}.")
                continue
            voted = set(dev_portal.json()['users'][0]['voted_ids'])
            db.session.add_all(UserLike(user_id=uid, app_id=x) for x in voted if x in known_apps)
            db.session.commit()
            print(f"Imported {len(voted)} likes.")
    print("Done.")


@apps.command('generate-index')
def generate_index():
    apps = App.query.order_by(App.id)
    result = []
    for app in apps:
        result.append(algolia_app(app))
    print(flask.json.dumps(result, indent=2))

@apps.command('update-patched-release')
@click.argument('new_pbw')
@click.argument('patchlvl')
def update_patched_release(new_pbw, patchlvl):
    release_id = os.path.basename(new_pbw).split('.')[0]
    release_old = Release.query.filter_by(id=release_id).one()
    if release_old.version is None:
        newvers = patchlvl
    else:
        newvers = f"{release_old.version}-{patchlvl}"
    release_new = release_from_pbw(release_old.app, new_pbw,
                                   release_notes = "Automatic maintenance patch from Rebble.",
                                   published_date = datetime.datetime.utcnow(),
                                   version = newvers,
                                   compatibility = release_old.compatibility)
    print(f"Uploading new version {newvers} of {release_old.app.id} ({release_old.app.title})...")
    upload_pbw(release_new, new_pbw)
    db.session.commit()

@apps.command('new-release')
@click.argument('pbw_file')
@click.argument('release_notes')
def new_release(pbw_file, release_notes):
    pbw = PBW(pbw_file, 'aplite')
    with pbw.zip.open('appinfo.json') as f:
        j = json.load(f)
    uuid = j['uuid']
    version = j['versionLabel']
    app = App.query.filter_by(app_uuid = uuid).one()
    release_old = Release.query.filter_by(app = app).order_by(Release.published_date).limit(1).one()
    print(f"Previous version {release_old.version}, new version {version}, release notes {release_old.release_notes}")
    if version == release_old.version:
        version = f"{version}-rbl"
    release_new = release_from_pbw(app, pbw_file,
                                   release_notes = release_notes,
                                   published_date = datetime.datetime.utcnow(),
                                   version = version,
                                   compatibility = release_old.compatibility)
    print(f"Uploading new version {version} of {release_old.app.id} ({release_old.app.title})...")
    upload_pbw(release_new, pbw_file)
    db.session.commit()

@apps.command('new-app')
@click.argument('conf')
def new_app(conf):
    params = yaml.load(open(conf, "r"))

    pbw_file = params['pbw_file']
    pbw = PBW(pbw_file, 'aplite')
    with pbw.zip.open('appinfo.json') as f:
        appinfo = json.load(f)
    
    if App.query.filter(App.app_uuid == appinfo['uuid']).count() > 0:
        raise ValueError("app already exists!")
    
    if 'developer_id' in params:
        developer = Developer.query.filter(Developer.id == params['developer_id']).one()
    else:
        developer = Developer(id = id_generator.generate(), name = appinfo['companyName'])
        db.session.add(developer)
    
    header_asset = upload_asset(params['header'])
    
    app_obj = App(
        id = id_generator.generate(),
        app_uuid = appinfo['uuid'],
        asset_collections = { x['name']: AssetCollection(
            platform=x['name'],
            description=params['description'],
            screenshots=[upload_asset(s) for s in x['screenshots']],
            headers = [header_asset],
            banner = None
        ) for x in params['assets']},
        category_id = category_map[params['category']],
        companions = {}, # companions not supported yet
        created_at = datetime.datetime.utcnow(),
        developer = developer,
        hearts = 0,
        releases = [],
        icon_large = upload_asset(params['large_icon']),
        icon_small = upload_asset(params['small_icon']),
        source = params['source'],
        title = params['title'],
        type = params['type'],
        timeline_enabled = False,
        website = params['website']
    )
    db.session.add(app_obj)
    print(f"Created app {app_obj.id}")
    
    release = release_from_pbw(app_obj, pbw_file,
                               release_notes = params['release_notes'],
                               published_date = datetime.datetime.utcnow(),
                               version = appinfo['versionLabel'],
                               compatibility = appinfo['targetPlatforms'])
    print(f"Created release {release.id}")
    upload_pbw(release, pbw_file)
    db.session.commit()
    
    if algolia_index:
        algolia_index.partial_update_objects([algolia_app(app_obj)], { 'createIfNotExists': True })

def init_app(app):
    app.cli.add_command(apps)
