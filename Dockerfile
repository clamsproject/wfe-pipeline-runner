FROM clamsproject/clams-python:0.5.1

# Used for debugging, can be removed to save space
RUN apt-get -y update && apt-get -y install curl vim

# Most of the requirements from requirements.txt are already installed in
# clamsproject/clams-python:0.5.1
RUN pip3 install pyyaml==5.4.1

WORKDIR ./app

COPY ./*.py ./
COPY ./examples/mmif ./examples/mmif
