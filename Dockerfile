FROM python:3.6-slim-buster

# Used for debugging, can be removed to save space
RUN apt-get -y update && apt-get -y install curl vim

WORKDIR ./app

COPY ./requirements.txt .

RUN pip3 install -r requirements.txt

COPY ./*.py ./
COPY ./examples/mmif ./examples/mmif
