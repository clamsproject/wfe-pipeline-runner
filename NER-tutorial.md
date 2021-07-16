# CLAMS-NER Tutorial

How to run spaCY NER on MMIF files. This document is specific to running an NER pipeline. It won't hurt to check out `README.md`, which is more general and which will eventually have all that is worthwhile reading.

You need Python 3.6 or higher, with the `PyYAML`, `requests` and `clams-python` packages.

```
$ pip3 install -r requirements.txt
```



## Preparation

Get the repositories, build the required Docker images, get your MMIF file, and create a configuration file.

You need the following repositories:

- [https://github.com/clamsproject/app-spacy-nlp](https://github.com/clamsproject/app-spacy-nlp)
- [https://github.com/clamsproject/pipeline-runner](https://github.com/clamsproject/pipeline-runner)
- [https://github.com/clamsproject/app-nlp-example](https://github.com/clamsproject/app-nlp-example)

The first is an absolute necessity, the second you need to run the pipeline script, but if you want to use your own scripts that would work, the third is optional and is here just to show how you run NER as the second step in a pipeline.

Clone these repositories to your machine and create an image for each one:

```
$ cd <SPACY_REPO_DIR>
$ docker build -t clams-spacy-nlp .
$ cd <PIPELINE_REPO_DIR>
$ docker build -t clams-pipeline .
$ cd <EXAMPLE_REPO_DIR>
$ docker build -t clams-nlp-example .
```

None of those images make any assumptions on what volumes to share or what URLs to expose, that is done later.

Your MMIF files probably look like this.

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
  ],
  "views": []
}
```

You have a video and an associtated transcript. The location of the source documents embodies one assumption which has been our convention all along: the application has access to a directory `/data` which has subdirectories for each document type.

Finally, if you use the pipeline script, you will need a configuration file.

```yaml
data: ${PWD}/examples/data

pipeline:
  image: clams-pipeline
  container: pipeline

services:
  - tokenizer:
      image: clams-nlp-example
      container: pipeline_tokenizer
  - spacy:
      image: clams-spacy-nlp
      container: pipeline_spacy
```

This script is included in the pipeline repository at `config/tokenizer-spacy.yml`. The first line indicates what local directory is to be connected to the `/data` directory for all applications. This has to be an absolute path. The second block tells you what image to use for the pipeline script and what to name the container. Finally the services are enumerated, again using names of existing images. Use whatever container names you deem appropriate.



## Firing up the pipeline

You can do this by using the pipeline code or by doing it all manually. The first is easier, the second gives you more control.

**Option 1: using the pipeline script**

Just run this command.

```
$ python start_pipeline.py config/tokenizer-spacy.yml
```

This creates two configuration files (`config.yml` and `docker-compose.yml`) and then runs the `docker-compose up -d` command to start up all containers. The configuration files are saved in the current directory of your Docker host AND in the application directory on the pipeline image. Now all containers are running.

```
$ docker ps --format " {{.ID}}  {{.Image}}  {{.Names}}  {{.Ports}} "
97d275be6492  clams-nlp-example  pipeline_tokenizer  0.0.0.0:5001->5000/tcp
650e8a414e29  clams-spacy-nlp    pipeline_spacy      0.0.0.0:5002->5000/tcp
c4b8c9f50899  clams-pipeline     pipeline
```

The `start_pipeline.py` assigns hostnames and ports to all application containers and exposes them to the Docker host (your local machine). It also created a network named `pipeline-runner_default` from within which containers can refer to eachother by name.

```
$ docker network ls -f driver=bridge
NETWORK ID     NAME                      DRIVER    SCOPE
8733c49d3009   bridge                    bridge    local
41e22fb402d8   pipeline-runner_default   bridge    local
```

**Option 2: doing it by hand**

You can do this manually by starting all applications by hand and then writing a script that uses curl or some other tool to access the services. For the latter part you are on your own, but this is how you would start the containers (this assumes there are no containers running with the names specified below).

```
$ docker run --rm -d -p 5001:5000 -v ${PWD}/examples/data:/data --name pipeline_tokenizer clams-nlp-example
$ docker run --rm -d -p 5002:5000 -v ${PWD}/examples/data:/data --name pipeline_spacy clams-spacy-nlp
```

The result is similar to the above.

```
$ docker ps --format " {{.ID}} {{.Image}} {{.Names}} {{.Ports}} "
9d469856042b  clams-spacy-nlp    pipeline_spacy      0.0.0.0:5001->5000/tcp
925ad8ff9d6c  clams-nlp-example  pipeline_tokenizer  0.0.0.0:5002->5000/tcp
```

You can play with the port numbers and the volume mount and deal with the output of an application in any way you like. There are some disadvantages:

- As started above, the containers cannot be accessed from another container, only from the host.
- Parameters have to be handed in manually.



## Running the pipeline

This is only for those who use the pipeline script, if you don't you are on your own.

Run the pipeline as follows.

```
$ python run_pipeline.py -iv examples/mmif/tokenizer-spacy-1.json out.json
Services in pipeline:
    <Service tokenizer pipeline_tokenizer http://0.0.0.0:5001/ >
    <Service spacy pipeline_spacy http://0.0.0.0:5002/ >
>>> examples/mmif/tokenizer-spacy-1.json
...running tokenizer
...running spacy
Statistics for each view in out.json
    v_0 app=https://apps.clams.ai/tokenizer time=0.03s status=OKAY - 24 annotations
    v_1 app=https://apps.clams.ai/spacy_nlp time=0.04s status=OKAY - 42 annotations
```

This runs the pipeline that you had configured in the beginning. The -v options prints stuff like the above (without it nothing would have been printed), the -i saves intermediate results.

You can run part of the pipeline by removing services in `config.yml` (which was automatically generated from your configuration file), for example, if you delete the spacy lines only the tokenizer will run.

You can also add parameters by editing `config.py`.

```yaml
data: ${PWD}/examples/data

pipeline:
  image: clams-pipeline
  container: pipeline

services:
  - tokenizer:
      image: clams-nlp-example
      container: pipeline_tokenizer
  - spacy:
      image: clams-spacy-nlp
      container: pipeline_spacy
      parameters:
        pretty: True
```

By the way, you need to be careful with this file, no tabs allowed.

The spacy application doesn't really have any parameters yet but there is at the generic `pretty` parameter which you can use the pretty print the output.

### Errors

If there was an error in one or more of the scripts you would see something like the following.

```
python run_pipeline.py -v examples/mmif/tokenizer-spacy-1.json xxx
Services in pipeline:
    <Service tokenizer pipeline_tokenizer http://0.0.0.0:5001/ >
    <Service spacy pipeline_spacy http://0.0.0.0:5002/ >
>>> examples/mmif/tokenizer-spacy-1.json
...running tokenizer
...running spacy
Statistics for each view in xxx
    v_0 app=https://apps.clams.ai/tokenizer time=0.03s status=OKAY - 24 annotations
    v_1 app=https://apps.clams.ai/spacy_nlp time=0.02s status=ERROR - json.decoder.JSONDecodeError: Extra data: line 1 column 3244 (char 3243)
```

Without the -v option you would not see this, but you can inspect the view metadata for errors. In the above case the tokenizer view has the following metadata.

```json
{
  "timestamp": "2021-05-06T12:38:34.069003",
  "app": "https://apps.clams.ai/tokenizer",
  "contains": {
    "http://vocab.lappsgrid.org/Token": {
      "document": "d2"
  }
}
```

The metadata includes a `contains` section which specifies what kind of annotations were added in the view and those annotations will be in the `annotations` property of the views (which can be empty is the CLAMS application didn't find any).

But the spaCy service returned and error and in that case the view will not have a `contains` propery but instead an `error` property.

```json
{
  "timestamp": "2021-05-06T08:38:34.089165",
  "app": "https://apps.clams.ai/spacy_nlp",
  "error": {
    "message": "json.decoder.JSONDecodeError: Extra data: line 1 column 3244 (char 3243)",
    "stackTrace": "Traceback (most recent call last):\n  File \"/usr/local/lib/python3.6/site-packages/clams/restify/__init__.py\", line 93, in post\n    return self.json_to_response(self.cla.annotate(Mmif(request.get_data()),\n  File \"/usr/local/lib/python3.6/site-packages/mmif/serialize/mmif.py\", line 41, in __init__\n    self.validate(mmif_obj)\n  File \"/usr/local/lib/python3.6/site-packages/mmif/serialize/mmif.py\", line 73, in validate\n    json_str = json.loads(json_str)\n  File \"/usr/local/lib/python3.6/json/__init__.py\", line 354, in loads\n    return _default_decoder.decode(s)\n  File \"/usr/local/lib/python3.6/json/decoder.py\", line 342, in decode\n    raise JSONDecodeError(\"Extra data\", s, end)\njson.decoder.JSONDecodeError: Extra data: line 1 column 3244 (char 3243)\n"
  }
}
```

The error always comes with a message and optionally with a stack trace.

> Services are set up so that they always return a MMIF object, you need to inspect the object to see whether an error occured. The pipeline code does that for you and prints notes to the output when using verbose mode. There is currently no logging facility. The pipeline code also catches some other errors (for example when no request could be sent to the service) and then still makes sure the ultimate result is valid MMIF.

After an error the pipeline code will by default try to merrily run all other elements in the pipeline. You can suppress that by using  the `--abort` option, in that case the code will just output the result of the last pipeline step with the error message and not apply any other steps. It will continue to the next file if you were processing a directory.
