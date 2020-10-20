"""pipeline.py

Running a pipeline of CLAMS applications from the command line. Assumes that
appplications are up and running as Fask services and that they were started
using docker-compose.yml. See README.md for more details.

Usage:

$ python3 pipeline.py [OPTIONS] INPATH OUTPATH APPLICATION*

The INPATH can be a file or a directory, in the latter case all files in the
directory will be processed. OUTPATH may not exist and will be created. The list
of applications should be the names of the services as used in the configuration
in docker-compose.yml. It may be empty, in which case a default list is created
from the config file, using the port number to order the services.

Examples:

$ python pipeline.py example-mmif.json example-mmif-out.json
$ python pipeline.py example-mmif.json example-mmif-out.json tokenizer spacy

OPTIONS:
  -h, --help           prints help message and exits
  -v, --verbose        prints some progress messages to standard output
  -i, --intermediate   writes intermediate files as well

"""

import os
import sys
import json
import yaml
import argparse
from operator import itemgetter

import requests


class Services(object):

    """Holds the names of services and their URLs, where the names and URLs are
    taken from a docker compose configuration file."""

    def __init__(self, fname):
        """Build a dictionary of service names and their URL."""
        with open(fname, 'r') as fh:
            specs = yaml.safe_load(fh)
        self.services = {}
        services = specs['services']
        for service in services:
            port = services[service]['ports'][0].split(':')[0]
            self.services[service] = 'http://0.0.0.0:%s/' % port

    def __getitem__(self, i):
        return self.services[i]

    def __str__(self):
        return "<Services %s>" % ','.join(self.service_names())

    def service_names(self):
        """Returns service names sorted on port number."""
        return [k for k,v in sorted(self.services.items(), key=itemgetter(1))]

    def metadata(self, service_name):
        url = self.services[service_name]
        try:
            response = requests.get(url)
            return response.json()
        except requests.exceptions.ConnectionError as e:
            print(">>> WARNING: error connecting to %s, returning empty metadata" % url)
            return {}

    def run(self, service_name, input_string):
        url = self.services.get(service_name)
        try:
            response = requests.put(url, data=input_string)
            return response.text
        except requests.exceptions.ConnectionError as e:
            print(">>> WARNING: error connecting to %s, returning input MMIF" % url)
            return None


class Pipeline(object):

    """To create a pipeline you first collect all services from the docker compose
    configuration file and then set the pipeline, generate the pipeline from the
    configuration if the pipeline handed in is the empty list."""

    def __init__(self, pipeline):
        self.services = Services('docker-compose.yml')
        self.pipeline = pipeline if pipeline else self.services.service_names()

    def __str__(self):
        return "<Pipeline %s>" % ('|'.join(self.pipeline))

    def run(self, in_path, out_path, verbose=False, intermediate=False):
        self.verbose = verbose
        self.intermediate = intermediate
        if os.path.exists(out_path):
            exit("ERROR: output file or directory already exist, exiting...")
        if os.path.isfile(in_path):
            self.run_on_file(in_path, out_path)
        elif os.path.isdir(in_path):
            os.mkdir(out_path)
            for fname in os.listdir(in_path):
                infile = os.path.join(in_path, fname)
                outfile = os.path.join(out_path, fname)
                if os.path.isfile(infile):
                    try:
                        self.run_on_file(infile, outfile)
                    except Exception as e:
                        print("WARNING: error on '%s': %s" % (fname, e))

    def run_on_file(self, infile, outfile):
        if self.verbose:
            print('Processing %s' % infile)
        mmif_string = open(infile).read()
        result = None
        step = 0
        for service in self.pipeline:
            if self.verbose:
                print("...running %s" % service)
            step += 1
            input_string = mmif_string if result is None else result
            # not using the metadata at the moment
            # metadata = self.services.metadata(service)
            result = self.services.run(service, input_string)
            result = input_string if result is None else result
            if self.intermediate:
                out = outfile[:-5] if outfile.endswith('.json') else outfile
                with open("%s-%d-%s.json" % (out, step, service), 'w') as fh:
                    fh.write(result)
        with open(outfile, 'w') as fh:
            fh.write(result)


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("INPUT", help="the input file or directory")
    parser.add_argument("OUTPUT", help="the output file or directory")
    parser.add_argument("PIPELINE", nargs='*', help="optional pipeline elements")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print some progress messages to standard output")
    parser.add_argument("-i", "--intermediate", action="store_true",
                        help="save intermediate files")
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    pipeline = Pipeline(args.PIPELINE)
    pipeline.run(args.INPUT, args.OUTPUT, args.verbose, args.intermediate)
