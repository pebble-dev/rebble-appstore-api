import json
import boto3
from botocore.exceptions import ClientError
from .models import Binary
from .settings import config
from .utils import id_generator

# Try to find a way to get S3 credentials.
session = None
s3_endpoint = None

try:
    if session is None:
        with open('session-token.json', 'r') as f:
            creds = json.load(f)
        session = boto3.Session(
            aws_access_key_id = creds['Credentials']['AccessKeyId'],
            aws_secret_access_key = creds['Credentials']['SecretAccessKey'],
            aws_session_token = creds['Credentials'].get('SessionToken'),
        )
        s3_endpoint = creds.get('S3Endpoint')
except:
    pass

if not session:
    print("no session")

def upload_pbw(release, file):
    filename = f"{config['S3_PATH']}{release.id}.pbw"

    if isinstance(file, str):
        print(f"uploading file {file} to {config['S3_BUCKET']}:{filename}")
        s3 = session.client('s3', endpoint_url=s3_endpoint)
        s3.upload_file(file, config['S3_BUCKET'], filename)
    else:
        print(f"uploading file object {file.name} to {config['S3_BUCKET']}:{filename}")   
        s3 = session.client('s3', endpoint_url=s3_endpoint)
        s3.upload_fileobj(file, config['S3_BUCKET'], filename, ExtraArgs = {'ContentType': 'application/zip'})   

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
                raise Exception(f"Unknown or unsupported mime_type for file provided to update_asset")

        s3 = session.client('s3', endpoint_url=s3_endpoint)
        s3.upload_file(file, config['S3_ASSET_BUCKET'], filename, ExtraArgs = {'ContentType': mime_type})
        return id
    
    else:
        print(f"uploading file object '{file.name}' to {config['S3_ASSET_BUCKET']}:{filename}")
        s3 = session.client('s3', endpoint_url=s3_endpoint)
        s3.upload_fileobj(file, config['S3_ASSET_BUCKET'], filename, ExtraArgs = {'ContentType': mime_type})
    
    return id    
