# pipeline-runner

Code to run a CLAMS pipeline from the command line.

It might make sense for this to be included in [https://github.com/clamsproject/appliance](https://github.com/clamsproject/appliance), but let's see where this goes.

Requirements:

- docker and docker-compose
- Python 3, with the `PyYAML` and `requests` packages
- git

```bash
$ pip3 install pyyaml requests
```

In addition you will need access to the applications, either by having the Docker image available locally or by a pull, or by having the repositories for the applications, including the Dockerfile that buids the Docker image.

### Starting the applications

The pipeline runner script in `pipeline.py` assumes there are Docker containers running for each application that is used by the pipeline, you do this by creating a `docker-compose.yml` configuration file and then running docker-compose. Here is an example configuration file:

```yaml
version: '3'

services:
  
  tokenizer:
    image: clams-tokenizer
    build:
      dockerfile: Dockerfile
      context: ../app-nlp-example
    ports:
      - '5001:5000'

  spacy:
    image: clams-spacy
    build:
      dockerfile: Dockerfile
      context: ../app-spacy-nlp
    ports:
      - '5002:5000'
```

This defines a bunch of containers that each run a Flask server on its standard port 5000, but exposing that port under a different port number so we can access all applications. For each service we define a name (here `tokenizer` and `spacy`), an image name, a build context and the port that will be exposed to the outside world. The file refers to the images `clams-tokenizer` and `clams-spacy`, which will be taken from the local images or pulled from Docker Hub (https://hub.docker.com/), if no image is available it will be built using the specifications in the *build* property. In this example we assume that the tokenizer and spacy repositories are in sister directories and it is you responsibility to get them there or put them elsewhere and update the *context* properties. 

> If we take the iages from Docker Hub then we do not need the build property. Note that in that case the name is likely to be different, for now we just work with local repositories and images.

We can now start up all applications:

```bash
$ docker-compose up -d
```

This pulls or creates images if needed and runs the containers, each of which is a Flask server with access to an CLAMS tool. You can see them listed:

```bash
$ docker ps --format "{{.Ports}}  {{.ID}}  {{.Image}}  {{.Names}}"
0.0.0.0:5001->5000/tcp  0bf79ffe1085  clams-tokenizer  pipelinerunner_tokenizer_1
0.0.0.0:5002->5000/tcp  2a80d31b1e02  clams-spacy  pipelinerunner_spacy_1
```

The container names are auto generated and use the name of this directory as a prefix.

You can take down the applications with `docker-compose down`.

### Running the pipeline script

We can then run the `pipeline.py` script which uses the `docker-compose.yml` configuration file to figure out what services are available. You give it a file as a parameter and optionally a pipeline, if no pipeline is given then a default pipeline will be created from the available service, ranked on port number.

> So if you carefully define the exposed port numbers in the configuration then the configuration file defines the pipeline.

Example 1, using the default pipeline:

```bash
$ python pipeline.py example-mmif.json
Running tokenizer
Running spacy
$ ls -al out*
-rw-r--r--  1 marc  staff  10344 Oct 16 13:23 out-1-tokenizer.json
-rw-r--r--  1 marc  staff  26325 Oct 16 13:23 out-2-spacy.json
```

All results, including intermediary result, are written to this directory.

Example 2, name the pipeline explicitly, which here has the same results as for example 1:

```bash
$ python pipeline.py example-mmif.json tokenizer spacy
Running tokenizer
Running spacy
$ ls -al out*
-rw-r--r--  1 marc  staff  10344 Oct 16 13:24 out-1-tokenizer.json
-rw-r--r--  1 marc  staff  26325 Oct 16 13:24 out-2-spacy.json
```

Example 3, hand in a different pipeline:

```bash
$ python pipeline.py example-mmif.json spacy tokenizer
Running spacy
Running tokenizer
$ ls -al out*
-rw-r--r--  1 marc  staff  19097 Oct 16 13:25 out-1-spacy.json
-rw-r--r--  1 marc  staff  26325 Oct 16 13:25 out-2-tokenizer.json
```

You will note the differences in file names and the different file size of the intermediate file (because the two services add different amounts of annotations). Note that this is not much of a pipeline since neither of the two steps depend of output of the other.

We could also have given just a single step pipeline, in which case there would be only one output file.

TODO:

- add option for processing an entire directory
- add option for processing an entire directory
- add output file (or directory) as an argument
- add switch for printing debugging output
- add switch to supress creation of intermediate files (could be part of debugging)
- have example where one service depends on the output of the other



