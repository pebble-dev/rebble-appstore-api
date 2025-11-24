# This is a slightly modified version of the PebbleBundle in libpebble2.
__author__ = 'katharine'

import json
import os
import io
import struct
import uuid
import zipfile
import datetime
import hashlib
from .models import Binary, Release, db
from .utils import id_generator

PLATFORMS = ['aplite', 'basalt', 'chalk', 'diorite', 'emery', 'flint']
GENERATED_ID_PREFIX = "13371337"

class PBW(object):
    MANIFEST_FILENAME = 'manifest.json'
    UNIVERSAL_FILES = {'appinfo.json', 'pebble-js-app.js'}

    STRUCT_DEFINITION = [
            '8s',   # header
            '2B',   # struct version
            '2B',   # sdk version
            '2B',   # app version
            'H',    # size
            'I',    # offset
            'I',    # crc
            '32s',  # app name
            '32s',  # company name
            'I',    # icon resource id
            'I',    # symbol table address
            'I',    # flags
            'I',    # num relocation list entries
            '16s'   # uuid
    ]

    PLATFORM_PATHS = {
        'aplite': ('aplite/', ''),
        'basalt': ('basalt/',),
        'chalk': ('chalk/',),
        'diorite': ('diorite/',),
        'emery': ('emery/',),
        'flint': ('flint/',),
    }

    def __init__(self, pbw, platform):
        self.platform = platform
        # pbw can be file path or bytes bundle. Determine which
        if isinstance(pbw, str):
            bundle_abs_path = os.path.abspath(pbw)
            if not os.path.exists(bundle_abs_path):
                raise Exception("Bundle does not exist: " + pbw)

            self.path = bundle_abs_path
        else:
            bundle = io.BytesIO(pbw)

        self.zip = zipfile.ZipFile(bundle)
        self.manifest = None
        self.header = None
        self._zip_contents = set(self.zip.namelist())

        self.app_metadata_struct = struct.Struct(''.join(self.STRUCT_DEFINITION))
        self.app_metadata_length_bytes = self.app_metadata_struct.size

        self.print_pbl_logs = False

    @classmethod
    def prefixes_for_platform(cls, platform):
        return cls.PLATFORM_PATHS[platform]

    def get_real_path(self, path):
        if path in self.UNIVERSAL_FILES:
            return path
        else:
            prefixes = self.prefixes_for_platform(self.platform)
            for prefix in prefixes:
                real_path = prefix + path
                if real_path in self._zip_contents:
                    return real_path
            return None

    def get_manifest(self):
        if self.manifest:
            return self.manifest

        if self.get_real_path(self.MANIFEST_FILENAME) not in self.zip.namelist():
            raise FileNotFoundError("Could not find {}; are you sure this is a PebbleBundle?".format(self.MANIFEST_FILENAME))

        self.manifest = json.loads(self.zip.read(self.get_real_path(self.MANIFEST_FILENAME)).decode('utf-8'))
        return self.manifest

    def get_app_metadata(self):
        if self.header:
            return self.header

        app_manifest = self.get_manifest()['application']

        app_bin = self.zip.open(self.get_real_path(app_manifest['name'])).read()

        header = app_bin[0:self.app_metadata_length_bytes]
        values = self.app_metadata_struct.unpack(header)
        self.header = {
            'sentinel': values[0],
            'struct_version_major': values[1],
            'struct_version_minor': values[2],
            'sdk_version_major': values[3],
            'sdk_version_minor': values[4],
            'app_version_major': values[5],
            'app_version_minor': values[6],
            'app_size': values[7],
            'offset': values[8],
            'crc': values[9],
            'app_name': values[10].rstrip(b'\0').decode('utf-8'),
            'company_name': values[11].rstrip(b'\0').decode('utf-8'),
            'icon_resource_id': values[12],
            'symbol_table_addr': values[13],
            'flags': values[14],
            'num_relocation_entries': values[15],
            'uuid': uuid.UUID(bytes=values[16])
        }
        return self.header

    def is_generated(self):
        with self.zip.open('appinfo.json') as f:
            appinfo = json.load(f)
            return str(appinfo["uuid"]).startswith(GENERATED_ID_PREFIX)

    def close(self):
        self.zip.close()

    @property
    def is_app_bundle(self):
        return 'application' in self.get_manifest()

    @property
    def has_resources(self):
        return 'resources' in self.get_manifest()

    @property
    def has_worker(self):
        return 'worker' in self.get_manifest()

    @property
    def has_javascript(self):
        return 'pebble-js-app.js' in [x.filename for x in self.zip.filelist]

    @property
    def has_platform(self):
        return self.get_real_path(self.MANIFEST_FILENAME) is not None

    def get_application_info(self):
        if not self.is_app_bundle:
            return None

        return self.get_manifest()['application']

    def get_resources_info(self):
        if not self.has_resources:
            return None

        return self.get_manifest()['resources']

    def get_worker_info(self):
        if not self.is_app_bundle or not self.has_worker:
            return None

        return self.get_manifest()['worker']

    def get_app_path(self):
        return self.get_real_path(self.get_application_info()['name'])

    def get_resource_path(self):
        return self.get_real_path(self.get_resources_info()['name'])

    def get_worker_path(self):
        return self.get_real_path(self.get_worker_info()['name'])

    def get_capabilities(self):
        with self.zip.open('appinfo.json') as f:
            return json.load(f).get('capabilities', [])
    
    def create_binary(self, release):
        if not self.has_platform:
            return
        metadata = self.get_app_metadata()
        binary = Binary(release=release, platform=self.platform,
                        sdk_major=metadata['sdk_version_major'], sdk_minor=metadata['sdk_version_minor'],
                        process_info_flags=metadata['flags'], icon_resource_id=metadata['icon_resource_id'])
        db.session.add(binary)
        
def release_from_pbw(app, bundle, release_notes=None, published_date=datetime.datetime.utcnow(), version='', compatibility=[]):
    pbw = PBW(bundle, 'aplite')
    js_md5 = None
    if pbw.has_javascript:
        with pbw.zip.open('pebble-js-app.js', 'r') as f:
            js_md5 = hashlib.md5(f.read()).hexdigest()
    release = Release(
        id=id_generator.generate(),
        app_id=app.id,
        has_pbw=True,
        capabilities=pbw.get_capabilities(),
        js_md5=js_md5,
        published_date=published_date,
        release_notes=release_notes,
        version=version,
        compatibility=compatibility,
        is_published=True,
    )
    db.session.add(release)
    
    for platform in PLATFORMS:
        pbw = PBW(bundle, platform)
        pbw.create_binary(release)
    
    return release
