FROM python:3.6-buster

# Only useful when you do some debugging
# RUN apt-get -y update && apt-get -y install curl emacs24

COPY ./ ./app
WORKDIR ./app

RUN pip3 install -r requirements.txt
