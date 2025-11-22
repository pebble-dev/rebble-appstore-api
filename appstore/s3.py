import json
import boto3
import threading
from botocore.exceptions import ClientError
from .models import Binary
from .settings import config
from .utils import id_generator

# Try to find a way to get S3 credentials.
session = None
s3_endpoint = None
session_lock = threading.Lock()

# Try loading creds from the environment.
try:
    if session is None and config['AWS_ACCESS_KEY'] is not None and config['AWS_SECRET_KEY'] is not None:
        session = boto3.Session(
            aws_access_key_id=config['AWS_ACCESS_KEY'],
            aws_secret_access_key=config['AWS_SECRET_KEY'],
        )
        s3_endpoint = config['S3_ENDPOINT']
except Exception:
    pass


# "Well, the creds were towed outside the environment."  "Into another
# environment?" "No, no, they've been towed beyond the environment.  They're
# not in the environment." "No, but from one environment to another
# environment." "No, it's beyond the environment.  It's not in an
# environment.  It's been towed beyond the environment." "Well, what's out
# there?" "Nothing's out there!" "Well there must be something out there"
# "There's nothing out there!  All there is sea, and birds, and fish."
# "And?" "And 20,000 tons of AWS creds." "And what else?" "And a fire."
#
# Try loading creds from an on-disk .json.
try:
    if session is None:
        with open('session-token.json', 'r') as f:
            creds = json.load(f)
        session = boto3.Session(
            aws_access_key_id=creds['Credentials']['AccessKeyId'],
            aws_secret_access_key=creds['Credentials']['SecretAccessKey'],
            aws_session_token=creds['Credentials'].get('SessionToken'),
        )
        s3_endpoint = creds.get('S3Endpoint')
except Exception:
    pass

if not session:
    print("no session")

_clients = {}

def _client_for_endpoint(endpoint):
    me = threading.current_thread()
    if (me, endpoint) in _clients:
        return _clients[(me, endpoint)]
    with session_lock:
        s3 = session.client('s3', endpoint_url=endpoint)
    _clients[(me, endpoint)] = s3
    return s3

def upload_pbw(release, file):
    filename = f"{config['S3_PATH']}{release.id}.pbw"

    if isinstance(file, str):
        print(f"uploading file {file} to {config['S3_BUCKET']}:{filename}")
        s3 = _client_for_endpoint(s3_endpoint)
        s3.upload_file(file, config['S3_BUCKET'], filename)
    else:
        print(f"uploading file object {file.name} to {config['S3_BUCKET']}:{filename}")   
        s3 = _client_for_endpoint(s3_endpoint)
        file.seek(0)
        s3.upload_fileobj(file, config['S3_BUCKET'], filename, ExtraArgs = {'ContentType': 'application/zip'})   

def download_pbw(id, file):
    filename = f"{config['S3_PATH']}{id}.pbw"
    s3 = _client_for_endpoint(s3_endpoint)
    if isinstance(file, str):
        s3.download_file(config['S3_BUCKET'], filename, file)
    else:
        s3.download_fileobj(config['S3_BUCKET'], filename, file)


def upload_asset(file, mime_type = None):
    id = id_generator.generate()
    filename = f"{config['S3_ASSET_PATH']}{id}"

    if isinstance(file, str):
        print(f"uploading file {file} to {config['S3_ASSET_BUCKET']}:{filename}")
        if mime_type is None:
            if file.endswith(".gif"):
                mime_type = "image/gif"
            elif file.endswith(".jpg") or file.endswith(".jpeg"):
                mime_type = "image/jpeg"
            elif file.endswith(".png"):
                mime_type = "image/png"
            else:
                raise Exception("Unknown or unsupported mime_type for file provided to update_asset")

        s3 = _client_for_endpoint(s3_endpoint)
        s3.upload_file(file, config['S3_ASSET_BUCKET'], filename, ExtraArgs = {'ContentType': mime_type})
        return id
    
    else:
        print(f"uploading file object '{file.name}' to {config['S3_ASSET_BUCKET']}:{filename}")
        file.seek(0)
        s3 = _client_for_endpoint(s3_endpoint)
        s3.upload_fileobj(file, config['S3_ASSET_BUCKET'], filename, ExtraArgs = {'ContentType': mime_type})
    
    return id    

def download_asset(id, file):
    filename = f"{config['S3_ASSET_PATH']}{id}"
    s3 = _client_for_endpoint(s3_endpoint)
    if isinstance(file, str):
        s3.download_file(config['S3_ASSET_BUCKET'], filename, file)
    else:
        s3.download_fileobj(config['S3_ASSET_BUCKET'], filename, file)
