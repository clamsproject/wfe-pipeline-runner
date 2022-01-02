# pipeline-runner

Code to run a CLAMS pipeline from the command line.

Requirements:

- docker and docker-compose
- Python 3.6 or higher, with the `PyYAML`, `requests` and `clams-python` packages (see `requirements.txt`)
- git (if you do not have the pipeline code yet)

To get the code and install the packages:

```bash
$ git clone https://github.com/clamsproject/pipeline-runner.git
$ pip3 install -r requirements.txt
```

In addition you will need access to the applications in the pipeline and the pipeline code itself by having the Docker images for all of them available locally or by a pull.

This document spells out how to run the pipeline and explains what is going on. If you know what your are doing and you have created a configuration file all you need to do is run two commands from the top-level of the repository, with the second one resulting in a MMIF file with the results of all processing:

```bash
$ python start_pipeline.py <configuration_file>
$ python run_pipeline.py examples/mmif/tokenizer-spacy-1.json out.json
```

There are three parts to this: (1) starting the CLAMS applications, (2) preparing your data and (3) running the pipeline. The rest of this documents first focuses on these three steps, in the last section we look at how to hand in parameters to individual applications.



### 1.  Starting the applications

The pipeline runner script in `run_pipeline.py` assumes there are Docker containers up and running for the pipeline code and each application that is used by the pipeline, it also assumes that those containers all have access to the same mounted directory. The `start_pipeline.py` script does that work for you given a fairly simple configuration file and a set of Docker images. These image will be taken from the list of locally available images or pulled from Docker Hub ([https://hub.docker.com/](https://hub.docker.com/)). At the moment, there are no images for CLAMS applications available on DockerHub and it is therefore your responsibility to build images locally. In particular, you need an image for the pipeline repository and one for each CLAMS application. This readme file is in the pipeline repository so in order to build the pipeline image using the Dockerfile all you need to do is

```bash
$ docker build -t clams-pipeline .
```

The CLAMS repositories in this example are available at:

- [https://github.com/clamsproject/app-nlp-example](https://github.com/clamsproject/app-nlp-example)
- [https://github.com/clamsproject/app-spacy-nlp](https://github.com/clamsproject/app-spacy-nlp)

See the instructions in those repositories on how to build the images. With the images available and the above configuration file we can start the pipeline as follows.

To start the containers needed for the pipeline we create a configuration file, here is an example configuration file for a pipeline with just a tokenizer and spaCy, this example is in this repository at `config/tokenizer-spacy.yml`.

```yaml
data: ${PWD}/examples/data

pipeline:
  image: clams-pipeline
  container: pipeline

services:
  - tokenizer:
      image: clams-nlp-example:0.0.6
      container: pipeline_tokenizer
  - spacy:
      image: clams-spacy-nlp:0.0.7
      container: pipeline_spacy
```

First we define a local directory that will be shared with the containers of all applications. In this case we take a directory inside this repository, but in real live it would typically be something like `/var/archive/data`. Note that the local directory has to be an absolute path, the use of `${PWD}` above ensures that for the subdirectory in this repository. Next we define the name of the pipeline container and the name of the image the container will be started from (`clams-pipeline`, which was used in the build command above). Finally we list the applications  (`tokenizer` and `spacy`) and for each one we specify the Docker image (`clams-nlp-example` and `clams-spacy-nlp`) and the name of the Docker container we create from the image. The container for a CLAMS app includes a Flask server with access to a CLAMS tool.

Now we can start the pipeline:

```bash
$ python start_pipeline.py config/tokenizer-spacy.yml
```

This does several things:

1. It creates a file `docker-compose.yml` in the top-level directory. This file specifies the names of containers for all applications, sets up the container's access to the shared data directory, and defines a port mapping for the each Flask server that runs an application in a container.
2. It copies `config/tokenizer-spacy.yml` to `config.yml` in the top-level directory.
3. It runs the `docker-compose up -d` command to start up the containers. The `docker-compose` command uses the images and starts containers, one for the pipeline script and one for each CLAMS application. In addition it mounts the data directory given in the configuration file to a directory `/data` on the container.
4. It copies `docker-compose.yml` and `config.yml` to the pipeline runner container.

At that point, all containers are up and all the configuration files needed for the pipeline script to run are available. You can list the containers.

```
$ docker ps --format " {{.ID}}  {{.Image}}  {{.Names}}  {{.Ports}} "
97d275be6492  clams-nlp-example:0.0.6	 pipeline_tokenizer  0.0.0.0:5001->5000/tcp
650e8a414e29  clams-spacy-nlp:0.0.7	   pipeline_spacy      0.0.0.0:5002->5000/tcp
c4b8c9f50899  clams-pipeline	         pipeline 	 
```

Note how the image and container names for the CLAMS applications and the pipeline code are taken directly from the original configuration file.

#### 1.1. The docker compose file

It is safe to skip this section if you are not interested in a look behind the screen on the docker compose file.

This is what the automatically generated `docker-compose.yml` looks like when we use the example configuration file above.

```yaml
version: '3'

services:

  pipeline:
    container_name: pipeline
    image: clams-pipeline
    stdin_open: true
    tty: true
    volumes:
      - "${PWD}/examples/data:/data"

  tokenizer:
    container_name: pipeline_tokenizer
    image: clams-nlp-example:0.0.6
    volumes:
      - "${PWD}/examples/data:/data"
    ports:
      - "5001:5000"

  spacy:
    container_name: pipeline_spacy
    image: clams-spacy-nlp:0.0.7
    volumes:
      - "${PWD}/examples/data:/data"
    ports:
      - "5002:5000"
```

When we run this script with `docker-compose up -d` three networked containers will be started. One container for the pipeline script and two containers for the two CLAMS applications. The two application containers are both running a Flask or GUnicorn server on their standard port 5000, but exposing that port under a different port number so we can access it from the outside.

A few remarks:

- We added the *stdin-open* and *tty* properties for the pipeline image to keep it from immediately exiting when you start it. This was not needed for the CLAMS application containers because they all run a command that starts a server.
- We use *volumes* to mount a local directory to a directory on containers created from the image. In the example we mount the local directory `examples/data` to `/data` on each container. We have some requirements on what is in the mounted directory:
  - It has four subdirectories, one for each document type: `video`, `text`, `audio` and `image`.
  - The subdirectories themselves have no substructure and just contain documents of the particular type that the sub directory is for. At some point this restriction may be relaxed.
- We use *ports* to define the port that will be exposed to the outside world. In the containers, Flask will run on port 5000, but we expose these ports as 5001 and 5002 to the terminal that the pipeline script runs from.

Port numbers are generated automatically and will be used if we run the pipeline script from a host, the container names are used if we run the pipline script from within the network, that is, from within the `pipeline` container.

To take down the application and its containers use `docker-compose down`. You need to do this before you can define and start another pipeline.



### 2.  Preparing your data

It is important to realize that the input to a pipeline is a MMIF file and not a video, audio, image or text document. The MMIF file refers to those documents but does not include them (even though optionally that might be the case for text documents). This gets a bit tricky when you realize that the MMIF file could be sent from the local machine where the pipeline script resides to a server on a container and therefore the documents referred to from the MMIF file must be accessible from the container.

In the running example we mounted a local directory to the `/data` directory on the container. For the explanation below we are assuming that we did not use `examples/data` but `/data/clams/archive`. With that in mind you can depict the flow when you run the pipeline script from your local machine as follows:

<img src="images/pipeline.jpg"/>

The pipeline runs on a MMIF file that points to a video document at`/data/video/927364.mp4 ` and a text document at `/data/text/927364.txt `. Those paths do not exist on the local machine from which you run the pipeline script, but they do exist on the server that the MMIF file is sent to as part of an HTTP request. The files `927364.mp4 ` and `927364.txt` do exist on the local machine, but in a different directory. And that directory is mounted to the `/data` directory on the container when we run `docker-compose up -d` which uses the *volumes* specification. Because of that specification, `/data/video/927364.mp4` on the container is the same as `/data/clams/archive/video/927364.mp4` on the local machine. The HHTP request is received by the server, the application code finds the documents on the server, does its thing and then returns a MMIF file (that last step is not shown in the figure).

When the MMIF file is created one has to be aware of what the directory structure on the container is. For simplicity we require that the mount point is always `/data` and we require that the directory we mount is as specified above with subdirectories for the four document types.

> You may feel that, ideally, the paths on the local machine and on the container should be the same. Sadly, that is not always possible, and that is why we end up with a local MMIF file that does not point to existing local paths.

The `clams-python` package has a utility command to create a MMIF file from primary documents. Typically, there is one primary document (a video), but there can be more, for example when there is a transcript associated with the video. You can use the `clams` command as follows:

```bash
$ clams source video:/data/video/927364.mp4 text:/data/text/927364.txt > 927364.json
```

This creates the following file:

```json
{
  "metadata": {
    "mmif": "http://mmif.clams.ai/0.4.0"
  },
  "documents": [
    {
      "@type": "http://mmif.clams.ai/0.4.0/vocabulary/VideoDocument",
      "properties": {
        "mime": "video",
        "location": "/data/video/927364.mp4",
        "id": "d1"
      }
    },
    {
      "@type": "http://mmif.clams.ai/0.4.0/vocabulary/TextDocument",
      "properties": {
        "mime": "text",
        "location": "/data/text/927364.txt",
        "id": "d2"
      }
    }
  ]
}
```

And this file, or any other file created as above, can be used as input to the pipeline script. Note that the `clams` command does not care whether the files you hand in actually exist. This is nice because we need to create the MMIF with paths that are relevant to the Docker container and those paths are not necessarily available on the host machine.



### 3.  Running the pipeline script

We can use the `run_pipeline.py` script and we can use it in two ways:

1. From the Docker host, where the CLAMS services are all running in their own containers and we access them from the host.
2. From the container where the pipeline code is running, by first connecting to that container.

#### 3.1.  Running from the docker host

The pipeline script uses the automatically generated configuration files `config.yml` and `docker-compose.yml` to figure out what services are made available to the pipeline. You give it a MMIF file as a parameter and optionally a list of services, if no services are given then a default pipeline of services will be created from all available services, ordered exactly as in the original configuration script.

Use -h to see the available options and arguments:

```
$ python run_pipeline.py -h
usage: run_pipeline.py [-h] [-v] [-i] [--params PARAMETERS] INPUT OUTPUT [PIPELINE [PIPELINE ...]]

positional arguments:
  INPUT                 the input file or directory
  OUTPUT                the output file or directory
  PIPELINE              optional pipeline elements

optional arguments:
  -h, --help            show this help message and exit
  -v, --verbose         print progress messages to standard output
  -i, --intermediate    save intermediate files
  --params PARAMETERS  parmaters for the pipeline components
```

Here is an example where we are using the default pipeline, while writing intermediate files:

```
$ python run_pipeline.py -iv examples/mmif/tokenizer-spacy-1.json out.json
Services in pipeline:
    <Service tokenizer pipeline_tokenizer http://0.0.0.0:5001/ >
    <Service spacy pipeline_spacy http://0.0.0.0:5002/ >
...running tokenizer
...running spacy
Statistics for each view in "out.json"
    v_0 app=https://apps.clams.ai/tokenizer time=0.04s status=OKAY - 24 annotations
    v_1 app=https://apps.clams.ai/spacy_nlp time=0.06s status=OKAY - 42 annotations
$ ls -al out*
-rw-r--r--   1 marc  staff   3241 Dec 27 16:11 out-1-tokenizer.json
-rw-r--r--   1 marc  staff   9845 Dec 27 16:11 out-2-spacy.json
-rw-r--r--   1 marc  staff   9845 Dec 27 16:11 out.json
```

As input, we can also use `examples/mmif/tokenizer-spacy-2.json`, which uses the `text` property instead of the `location` property to store the text, the output will be the same except for some bookkeeping.

Here we define the pipeline explicitly, switching the order relative to the default (and turning off verbose printing):

```
$ python run_pipeline.py -i examples/mmif/tokenizer-spacy-1.json out.json spacy tokenizer
$ ls -al out*
-rw-r--r--   1 marc  staff   6841 Dec 27 16:17 out-1-spacy.json
-rw-r--r--   1 marc  staff   9845 Dec 27 16:17 out-2-tokenizer.json
-rw-r--r--   1 marc  staff   9845 Dec 27 16:17 out.json
```

Note the differences in file names and the different file sizes of the intermediate files (because the two services add different amounts of annotations and they are added in different orders now). Also note that this is not much of a pipeline since neither of the two steps depend on the output of the other.

We could also have given just a single step pipeline, in which case there would be only one intermediate output file.

The approach painted here requires that all applications can be loaded at the same time, which in some cases may not be feasible. If running a complete pipeline runs into memory issues then you can use the pipeline script to successively run one-step pipelines over a directory. Assume we have two configuration scripts, one for just the tokenizer and one for Spacy. We can then run just the first step over all documents:

```bash
$ python start_pipeline.py config/tokenizer.yml
$ python run_pipeline.py examples/mmif out-tokenizer
```

Here we run the pipeline on a directory instead of on a file, in which case the pipeline will apply to all files in the directory. Results will be written to `out-tokenizer`.

We can now follow this up y running Spacy in batch after taking down the containers for the previous step.

```bash
$ docker-compose down
$ python start_pipeline.py config/spacy.yml
$ python run_pipeline.py out-tokenizer out-spacy
```

And now we also have a directory `out-spacy` with results of spacy processing.

#### 3.2.  Running from the pipeline container

This is very much the same as the above, except that we also need to log into the pipeline container. Let's assume we have already started the pipeline. We enter the pipeline container and then do exactly the same thing we did before when we did not run the pipeline from a container.

```
$ docker exec -it pipeline bash
root@29725a215e11:/app# python run_pipeline.py -v examples/mmif/tokenizer-spacy-1.json out.json
Processing examples/mmif/tokenizer-spacy-1.json
...running tokenizer
...running spacy
root@28042e000e87:/app# ls -al
total 52
drwxr-xr-x 1 root root    4096 Apr 29 15:47 .
drwxr-xr-x 1 root root    4096 Apr 29 15:44 ..
-rw-r--r-- 1  501 dialout  249 Apr 29 15:00 config.yml
-rw-r--r-- 1  501 dialout  493 Apr 29 15:44 docker-compose.yml
drwxr-xr-x 3 root root    4096 Apr 29 15:44 examples
-rw-r--r-- 1 root root    9845 Apr 29 15:47 out.json
-rw-r--r-- 1 root root      36 Dec  5 15:42 requirements.txt
-rw-r--r-- 1 root root    9208 Apr 29 15:36 run_pipeline.py
-rw-r--r-- 1 root root    2945 Apr 29 15:05 start_pipeline.py
```



### 4.  Errors

Some errors are caught including the following:

- Error generated by the appliction and reported in the view's metadata.
- Illegal parameters handed in by the pipeline script. These now cause errors and prevent the applicaiton from processsing the input.
- A request error raised when the post request is put in.

In all cases the application for which the error happened will return a MMIF object but the view that is added will not have annotaitons but an error message instead. The pipeline will try to continue, that behavior can be overruled by using the `--abort` option when invloking `run_pipeline.py`.



### 5.  Handing parameters to applications

Application can take parameters and we allow the initial configuration file to include parameters. For example, instead of `config/tokenizer-spacy.yml` we can use `config/tokenizer-spacy-params.yml` which looks as follows.

```yaml
data: ${PWD}/examples/data

pipeline:
  image: clams-pipeline
  container: pipeline

services:
  - tokenizer:
      image: clams-nlp-example:0.0.6
      container: pipeline_tokenizer
      parameters:
        eol: False
  - spacy:
      image: clams-spacy-nlp:0.0.7
      container: pipeline_spacy
      parameters:
        pretty: True
```

Added here are two parameters, one for the tokenizer and one for spaCy. With this you would still use `start_pipeline.py` and `run_pipeline.py` as before, and with the latter all the parameters in the configuration file will be handed in to the application. You can also edit `config.yml` before you run `run_pipeline.py` and the updated parameters will be handed in.

Notice that the tokenizer application needs to have defined `eol` as one of its parameters, if it doesn't using that parameter will result in an error.

You can also overrule parameters in `config.py` by using command line arguments.

```bash
$ python run_pipeline.py -iv --params tokenizer-eol=True examples/mmif/tokenizer-spacy-1.json out.json
```

 On the command line, parameters are added as a comma-separated string where all elements have the following syntax.

```
SERVICE_NAME-PARAMETER=VALUE
```

So you can do things like

```bash
--params tokenizer-eol=True
--params tokenizer-eol=True,tokenizer-pretty=True,spacy-linking=False
```

The `pretty` parameter can be used for any component and results in the output JSON being pretty printed.

