import json
import boto3
from botocore.exceptions import ClientError
from .models import Binary
from .settings import config
from .utils import id_generator

# Try to find a way to get S3 credentials.
session = None

try:
    if session is None:
        with open('session-token.json', 'r') as f:
            creds = json.load(f)
        session = boto3.Session(
            aws_access_key_id = creds['Credentials']['AccessKeyId'],
            aws_secret_access_key = creds['Credentials']['SecretAccessKey'],
            aws_session_token = creds['Credentials']['SessionToken']
        )
except:
    pass

if not session:
    print("no session")

def upload_pbw(release, file):
    filename = f"{config['S3_PATH']}{release.id}.pbw"
    print(f"uploading file {file} to {config['S3_BUCKET']}:{filename}")
    
    s3 = session.client('s3')
    s3.upload_file(file, config['S3_BUCKET'], filename)

def upload_asset(file, mime_type = "image/png"):
    id = id_generator.generate()
    filename = f"{config['S3_ASSET_PATH']}{id}"
    print(f"uploading file {file} to {config['S3_ASSET_BUCKET']}:{filename}")
    
    s3 = session.client('s3')
    s3.upload_file(file, config['S3_ASSET_BUCKET'], filename, ExtraArgs = {'ContentType': mime_type})
    
    return id
