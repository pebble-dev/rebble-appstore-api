import datetime
import shutil
import uuid
import zipfile

import click
import os
from flask.cli import AppGroup

import requests
from sqlalchemy.orm.exc import NoResultFound

from .utils import id_generator
from .models import Category, db, App, Developer, Release, CompanionApp, Binary, AssetCollection
from .pbw import PBW

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


@apps.command('import-apps')
@click.argument('app_type')
def import_apps(app_type):
    for app in fetch_apps(f"https://api2.getpebble.com/v2/apps/collection/all/{app_type}?hardware=basalt&filter_hardware=false&limit=100"):
        try:
            dev = Developer.query.filter_by(id=app['developer_id']).one()
        except NoResultFound:
            dev = Developer(id=app['developer_id'], name=app['author'])
            db.session.add(dev)
        print(f"Adding app: {app['title']} ({app.get('app_uuid')}, {app['id']})...")

        release = app.get('latest_release')
        if release:
            filename = f"pbws/{release['id']}.pbw"
            if not os.path.exists(filename):
                with requests.get(release['pbw_file'], stream=True) as r:
                    if r.status_code != 200:
                        print(f"FAILED to download pbw.")
                        continue
                    with open(filename, 'wb') as f:
                        shutil.copyfileobj(r.raw, f)
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
                    icon=v['icon'],
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
            icon_large=((app.get('list_image') or {}).get('144x144') or '').replace('/convert?cache=true&fit=crop&w=144&h=144', ''),
            icon_small=((app.get('icon_image') or {}).get('48x48') or '').replace('/convert?cache=true&fit=crop&w=48&h=48', ''),
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
                                         screenshots=[next(iter(x.values())) for x in data['screenshot_images']],
                                         headers=[next(iter(x.values())) for x in data['header_images']] if data.get('header_images') else [],
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


def init_app(app):
    app.cli.add_command(apps)
