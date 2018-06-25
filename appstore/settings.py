import os

domain_root = os.environ.get('DOMAIN_ROOT', 'rebble.io')

config = {
    'DOMAIN_ROOT': domain_root,
    'SQLALCHEMY_DATABASE_URI': os.environ['DATABASE_URL'],
    'PBW_ROOT': os.environ.get('PBW_ROOT', f'http://pbws.{domain_root}/pbw'),
    'IMAGE_ROOT': os.environ.get('IMAGE_ROOT', f'https://assets.rebble.io'),
    'APPSTORE_ROOT': os.environ.get('APPSTORE_ROOT', f'http://apps.{domain_root}'),
    'REBBLE_AUTH_URL': os.environ.get('REBBLE_AUTH_URL', f'http://auth.{domain_root}'),
    'ALGOLIA_APP_ID': os.environ.get('ALGOLIA_APP_ID'),
    'ALGOLIA_ADMIN_API_KEY': os.environ.get('ALGOLIA_ADMIN_API_KEY'),
    'ALGOLIA_INDEX': os.environ.get('ALGOLIA_INDEX'),
}
