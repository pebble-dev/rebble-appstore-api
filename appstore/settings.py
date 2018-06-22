import os

config = {
    'SQLALCHEMY_DATABASE_URI': os.environ['DATABASE_URL'],
    'PBW_ROOT': os.environ.get('PBW_ROOT', 'http://pbws.rebble.io/pbw'),
    'IMAGE_ROOT': os.environ.get('IMAGE_ROOT', 'https://assets.rebble.io'),
}
