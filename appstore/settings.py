import os

config = {
    'SQLALCHEMY_DATABASE_URI': os.environ['DATABASE_URL'],
    'PBW_ROOT': os.environ.get('PBW_ROOT', 'http://magic'),
    'IMAGE_ROOT': os.environ['IMAGE_ROOT'],
}
