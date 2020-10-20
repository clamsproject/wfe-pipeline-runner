# pipeline-runner

Code to run a CLAMS pipeline from the command line.

It might make sense for this to be included in [https://github.com/clamsproject/appliance](https://github.com/clamsproject/appliance), but let's see where this goes.

Requirements:

- docker and docker-compose
- Python 3, with the `PyYAML` and `requests` packages
- git

```bash
$ pip3 install pyyaml requests
$ https://github.com/clamsproject/pipeline-runner.git
$ cd pipeline-runner
```

In addition you will need access to the applications, either by having the Docker images available locally or by a pull, or by having the repositories for the applications, including the Dockerfile that builds the Docker image.

### Starting the applications

The pipeline runner script in `pipeline.py` assumes there are Docker containers running for each application that is used by the pipeline, you do this by creating a `docker-compose.yml` configuration file and then running docker-compose. Here is an example configuration file (included in this repository in the `examples` directory) :

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

This defines two containers that each run a Flask server on its standard port 5000, but exposing that port under a different port number so we can access all applications. For each service we define a name (here `tokenizer` and `spacy`), an image name, a build context and the port that will be exposed to the outside world. The file's *image* property refers to the images `clams-tokenizer` and `clams-spacy`, which will be taken from the local images or pulled from Docker Hub (https://hub.docker.com/), if no image is available it will be built using the specifications in the *build* property. In this example we assume that the tokenizer and spacy repositories are in sister directories; it is you responsibility to get them there or put them elsewhere and update the *context* properties.

> We do not need the build property if images are available locally or on Docker Hub. Note that in the latter case the name is likely to be different, for now we just work with local repositories and images.

We can now start up all applications:

```bash
$ cp examples/docker-compose.yml .
$ docker-compose up -d
```

This pulls or creates images if needed and runs the containers, each of which is a Flask server with access to a CLAMS tool. You can see them listed:

```bash
$ docker ps --format "{{.Ports}}  {{.ID}}  {{.Image}}  {{.Names}}"
0.0.0.0:5001->5000/tcp  0bf79ffe1085  clams-tokenizer  pipelinerunner_tokenizer_1
0.0.0.0:5002->5000/tcp  2a80d31b1e02  clams-spacy  pipelinerunner_spacy_1
```

The container names are auto generated and use the name of this directory as a prefix.

You can take down the applications with `docker-compose down`.

### Running the pipeline script

We can then run the `pipeline.py` script which uses the `docker-compose.yml` configuration file to figure out what services are available. You give it a file as a parameter and optionally a list of services, if no services are given then a default pipeline of services will be created from all available services, ordered on port number.

> So if you carefully define the exposed port numbers in the configuration then the configuration file defines the pipeline.

In its basic form the script itself takes input and output paths and an optional pipeline specification. Use the -h option to see the available options and arguments:

```bash
$ python pipeline.py -h
usage: pipeline.py [-h] [-v] [-i] INPUT OUTPUT [PIPELINE [PIPELINE ...]]

positional arguments:
  INPUT               the input file or directory
  OUTPUT              the output file or directory
  PIPELINE            optional pipeline elements

optional arguments:
  -h, --help          show this help message and exit
  -v, --verbose       print some progress messages to standard output
  -i, --intermediate  save intermediate files
```

Here is an example where we using the default pipeline, while writing intermediate files:

```bash
$ python pipeline.py -iv examples/mmif-east-tesseract.json out.json
Processing example-mmif.json
...running tokenizer
...running spacy
$ s -al out*
-rw-r--r--  1 marc  staff  10344 Oct 19 13:41 out-1-tokenizer.json
-rw-r--r--  1 marc  staff  26325 Oct 19 13:41 out-2-spacy.json
-rw-r--r--  1 marc  staff  26325 Oct 19 13:41 out.json
```

And here is one where we define the pipeline explicitly, switching the order relative to the default:

```bash
$ python pipeline.py -iv examples/mmif-east-tesseract.json out.json spacy tokenizer
Processing example-mmif.json
...running spacy
...running tokenizer
$ ls -al out*
-rw-r--r--  1 marc  staff  19097 Oct 19 13:45 out-1-spacy.json
-rw-r--r--  1 marc  staff  26325 Oct 19 13:45 out-2-tokenizer.json
-rw-r--r--  1 marc  staff  26325 Oct 19 13:45 out.json
```

Note the differences in file names and the different file size of the intermediate file (because the two services add different amounts of annotations). Also note that this is not much of a pipeline since neither of the two steps depend on the output of the other.

We could also have given just a single step pipeline, in which case there would be only one intermediate output file.
