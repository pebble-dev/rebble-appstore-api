aws --profile rebble sts get-session-token "$@" > session-token.json
echo export AWS_ACCESS_KEY_ID=$(jq -r .Credentials.AccessKeyId < session-token.json) AWS_SECRET_ACCESS_KEY=$(jq -r .Credentials.SecretAccessKey < session-token.json) AWS_SESSION_TOKEN=$(jq -r .Credentials.SessionToken < session-token.json) > aws-env.env
