FROM python:3.6-buster

# Only useful when you do some debugging
# RUN apt-get -y update && apt-get -y install curl emacs24

WORKDIR ./app

COPY ./pipeline.py .
COPY ./docker-compose.yml .
COPY ./requirements.txt .

RUN pip3 install -r requirements.txt
