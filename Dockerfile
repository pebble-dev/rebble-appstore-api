FROM python:3.6-alpine
RUN apk add --update build-base libffi-dev
RUN apk add --update postgresql-dev
ADD . /code
WORKDIR /code
RUN pip install -r requirements.txt
CMD ["flask", "run", "-h", "0.0.0.0"]
