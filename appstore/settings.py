import os

domain_root = os.environ.get('DOMAIN_ROOT', 'rebble.io')

config = {
    'DOMAIN_ROOT': domain_root,
    'SQLALCHEMY_DATABASE_URI': os.environ['DATABASE_URL'],
    'PBW_ROOT': os.environ.get('PBW_ROOT', f'http://pbws.{domain_root}/pbw'),
    'IMAGE_ROOT': os.environ.get('IMAGE_ROOT', f'http://assets.{domain_root}'),
    'REBBLE_AUTH_URL': os.environ.get('REBBLE_AUTH_URL', f'http://auth.{domain_root}')
}
