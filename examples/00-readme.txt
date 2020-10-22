This directory has example data for working with a pipeline.

If you want to use documents in here then mount this data directory to the /data
directory on the container. Typically, a mounted volume has video, audio, image
and text subdirectories, but for now, there is only a text subdirectory.

The mmif directory has some example MMIF files.

Current examples:

1. Example for running an NLP pipeline

Uses the MMIF file in mmif/east-tesseract.json and has links to a non-existing
video document and a text document in data/text/east-tesseract.txt. There is a
docker configuration file in docker/docker-compose-tokenizer-spacy.yml.

