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
  -v, --verbose        prints progress to standard output
  -i, --intermediate   writes intermediate files

"""

import os
import sys
import shutil
import json
import yaml
from operator import itemgetter

import requests
import argparse


# default docker compose file
CONFIGURATION_FILE = 'docker-compose.yml'

# prefix for the container name
CONTAINER_PREFIX = 'pipeline_'

PIPELINE_SERVICE = 'pipeline'


class Services(object):

    """Holds the names of services and their URLs, where the names and URLs are
    taken from a docker compose configuration file."""

    def __init__(self, fname):
        """Build a dictionary of service names and their URL."""
        with open(fname, 'r') as fh:
            specs = yaml.safe_load(fh)
        self.services = {}
        self.params = {}
        services = specs['services']
        for service in services:
            # Skipping the pipeline service itself since it should not run as a
            # step in the pipeline.
            if service == PIPELINE_SERVICE:
                continue
            port = services[service]['ports'][0].split(':')[0]
            # URL depends on whether the service runs in a container or not, so
            # here we give a pair with the first element reflecting the URL when
            # running outside a container and the second the URL from the
            # pipeline script running inside a container.
            self.services[service] = ('http://0.0.0.0:%s/' % port,
                                      'http://%s%s:5000/' % (CONTAINER_PREFIX, service))
                                      'http://clams_%s:5000/' % service)
            self.params[service] = services[service].get("parameters", {})

    def __getitem__(self, i):
        return self.services[i]

    def __str__(self):
        return "<Services %s>" % ','.join(self.service_names())

    def get_url(self, service_name):
        """Return the URL for the service, keeping in mind that the URL is different
        depending on whether you run from inside a container or from the host."""
        if host_mode():
            return self.services[service_name][1]
        else:
            return self.services[service_name][0]

    def get_params(self, service_name):
        return self.params[service_name]

    def service_names(self):
        """Returns service names sorted on port number."""
        return [k for k,v in sorted(self.services.items(), key=itemgetter(1))]

    def metadata(self, service_name):
        url = self.get_url(service_name)
        try:
            response = requests.get(url)
            # TODO: using json() gives an error for reasons I do not yet understand
            return response.text
        except requests.exceptions.ConnectionError as e:
            print(">>> WARNING: error connecting to %s, returning empty metadata" % url)
            return {}

    def run(self, service_name, input_string):
        url = self.get_url(service_name)
        params = self.get_params(service_name)
        try:
            response = requests.put(url, data=input_string, params=params)
            return response.text
        except requests.exceptions.ConnectionError as e:
            print(">>> WARNING: error connecting to %s, returning input MMIF" % url)
            return None


class Pipeline(object):

    """To create a pipeline you first collect all services from the docker compose
    configuration file and then set the pipeline, generate the pipeline from the
    configuration if the pipeline handed in is the empty list."""

    def __init__(self, pipeline, dockerfile=None):
        config_file = CONFIGURATION_FILE if dockerfile is None else dockerfile
        self.services = Services(config_file)
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
            # not using the metadata for now
            # metadata = self.services.metadata(service)
            result = self.services.run(service, input_string)
            result = input_string if result is None else result
            if self.intermediate:
                out = outfile[:-5] if outfile.endswith('.json') else outfile
                with open("%s-%d-%s.json" % (out, step, service), 'w') as fh:
                    fh.write(result)
        with open(outfile, 'w') as fh:
            fh.write(result)


def host_mode():
    """Returns True if a 'docker' executable is present; false otherwise. This
    is a simple heuristic to determine if we are running in a container or not,
    assuming that the 'docker' command WILL NOT be present when we are inside a
    container and WILL be present if we are on the host."""
    # NOTE: others suggested to check for the presence of the /.dockerenv file
    # TODO: maybe use a command line option to distinguish between the two cases
    return shutil.which('docker') is None


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("INPUT", help="the input file or directory")
    parser.add_argument("OUTPUT", help="the output file or directory")
    parser.add_argument("PIPELINE", nargs='*', help="optional pipeline elements")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print progress to standard output")
    parser.add_argument("-i", "--intermediate", action="store_true",
                        help="save intermediate files")
    parser.add_argument("--config", dest="config_file",
                        help="alternative docker-compose file")
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    pipeline = Pipeline(args.PIPELINE, args.config_file)
    print(pipeline)
    print(pipeline.services.services)
    pipeline.run(args.INPUT, args.OUTPUT, args.verbose, args.intermediate)
