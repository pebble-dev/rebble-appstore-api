import os

domain_root = os.environ.get('DOMAIN_ROOT', 'rebble.io')
http_protocol = os.environ.get('HTTP_PROTOCOL', 'https')

config = {
    'DOMAIN_ROOT': domain_root,
    'SQLALCHEMY_DATABASE_URI': os.environ['DATABASE_URL'],
    'PBW_ROOT': os.environ.get('PBW_ROOT', f'http://pbws.{domain_root}/pbw'),
    'IMAGE_ROOT': os.environ.get('IMAGE_ROOT', f'https://assets.rebble.io'),
    'APPSTORE_ROOT': os.environ.get('APPSTORE_ROOT', f'http://apps.{domain_root}'),
    'REBBLE_AUTH_URL': os.environ.get('REBBLE_AUTH_URL', f"{http_protocol}://auth.{domain_root}"),
    'ALGOLIA_APP_ID': os.environ.get('ALGOLIA_APP_ID'),
    'ALGOLIA_ADMIN_API_KEY': os.environ.get('ALGOLIA_ADMIN_API_KEY'),
    'ALGOLIA_INDEX': os.environ.get('ALGOLIA_INDEX'),
    'SECRET_KEY': os.environ.get('SECRET_KEY'),
    'S3_BUCKET': os.environ.get('S3_BUCKET', 'rebble-pbws'),
    'S3_PATH': os.environ.get('S3_PATH', 'pbw/'),
    'S3_ASSET_BUCKET': os.environ.get('S3_ASSET_BUCKET', 'rebble-appstore-assets'),
    'S3_ASSET_PATH': os.environ.get('S3_ASSET_PATH', ''),
    'S3_ARCHIVE_BUCKET': os.environ.get('S3_ARCHIVE_BUCKET', 'rebble-archive'),
    'S3_ARCHIVE_PATH':   os.environ.get('S3_ARCHIVE_PATH'  , 'appstore/'),
    'HONEYCOMB_KEY': os.environ.get('HONEYCOMB_KEY', None),
    'DISCORD_HOOK_URL': os.environ.get('DISCORD_HOOK_URL', None),
    'DISCORD_ADMIN_HOOK_URL': os.environ.get('DISCORD_ADMIN_HOOK_URL', None),
    'ALGOLIA_DISABLE': os.environ.get('ALGOLIA_DISABLE', False),
    'AWS_ACCESS_KEY': os.environ.get('AWS_ACCESS_KEY', None),
    'AWS_SECRET_KEY': os.environ.get('AWS_SECRET_KEY', None),
    'S3_ENDPOINT': os.environ.get('S3_ENDPOINT', None),
    'TEST_APP_UUID': os.environ.get('TEST_APP_UUID', None),
}
