FROM python:3.6-alpine
RUN apk add --update build-base libffi-dev zlib-dev jpeg-dev
RUN apk add --update postgresql-dev
COPY requirements.txt requirements.txt
RUN pip install -r requirements.txt
ADD . /code
WORKDIR /code
RUN pip install ./rws-common
ENV FLASK_ENV=development
CMD ["flask", "run", "-h", "0.0.0.0"]
