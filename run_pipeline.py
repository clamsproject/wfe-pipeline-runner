"""pipeline.py

Running a pipeline of CLAMS applications from the command line. Assumes that
appplications are up and running as Fask services and that they were started
using start_pipeline.py, which takes a configuration file as input. After that
script ran there should be two configuration files, both in the top-level
directory:

- config.py
- docker-compose.py

These files are used by this script to gather information about the services.

See README.md for more details.

Usage:

$ python3 run_pipeline.py [OPTIONS] INPATH OUTPATH APPLICATION*

The INPATH can be a file or a directory, in the latter case all files in the
directory will be processed. OUTPATH may not exist and will be created. The
names in the list of applications should be the names of the services as used in
the configuration file handed to start_pipeline.py (and saved as config.py). The
applications list may be empty, in which case a default list is created from the
config file, using the port number to order the services.

Examples:

$ python run_pipeline.py examples/mmif/tokenizer-spacy-1.json out.json
$ python run_pipeline.py examples/mmiftokenizer-spacy-1.json out.json tokenizer spacy

OPTIONS:
  -h, --help           show this help message and exit
  -v, --verbose        print progress to standard output
  -i, --intermediate   save intermediate files
  --params PARAMETERS  parmaters for the pipeline components

"""

import os
import sys
import shutil
import json
import yaml
import requests
import argparse
from operator import itemgetter


# configuration files
CONFIG_FILE = 'config.yml'
COMPOSE_FILE = 'docker-compose.yml'


class Services(object):

    """Holds the names of services and their URLs, where the names and URLs are
    taken from a docker compose configuration file."""

    def __init__(self, parameters):
        """Build a dictionary of service names and their URLs."""
        with open(COMPOSE_FILE, 'r') as fh1, open(CONFIG_FILE, 'r') as fh2:
            compose_specs = yaml.safe_load(fh1)
            config_specs = yaml.safe_load(fh2)
        self.service_urls = {}
        self.service_params = {}
        self._set_service_urls(config_specs, compose_specs)
        self._set_service_params(config_specs, parameters)

    def _set_service_urls(self, config_specs, compose_specs):
        for service in config_specs['services']:
            name, specs = list(service.items())[0]
            port = compose_specs['services'][name]['ports'][0].split(':')[0]
            # URL depends on whether the service runs in a container or not, so
            # here we give a pair with the first element reflecting the URL when
            # running outside a container and the second the URL from the
            # pipeline script running inside a container.
            self.service_urls[name] = (
                'http://0.0.0.0:%s/' % port,
                'http://%s:5000/' % specs['container'])

    def _set_service_params(self, config_specs, parameters):
        for service in config_specs['services']:
            service_name = list(service.keys())[0]
            service_params = service[service_name].get('parameters', {})
            self.service_params[service_name] = service_params
        if parameters is not None:
            for parameter in parameters.split(','):
                try:
                    name, value = parameter.split('=')
                    component, name = name.split('-', 1)
                    print(component, name, value)
                    self.service_params.setdefault(component, {})[name] = value
                except IndexError:
                    pass

    def __str__(self):
        return "<Services %s>" % ','.join(self.service_names())

    def get_url(self, service_name):
        """Return the URL for the service, keeping in mind that the URL is different
        depending on whether you run from inside a container or from the host."""
        if host_mode():
            return self.service_urls[service_name][1]
        else:
            return self.service_urls[service_name][0]

    def get_params(self, service_name):
        return self.service_params[service_name]

    def service_names(self):
        """Returns service names sorted on port number."""
        return [k for k,v in sorted(self.service_urls.items(), key=itemgetter(1))]

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

    def __init__(self, pipeline, parameters=None):
        self.services = Services(parameters)
        self.pipeline = pipeline if pipeline else self.services.service_names()

    def __str__(self):
        return "<Pipeline %s>" % ('|'.join(self.pipeline))

    def run(self, in_path, out_path, verbose=False, intermediate=False):
        self.verbose = verbose
        self.intermediate = intermediate
        if not os.path.exists(in_path):
            exit("ERROR: input file or directory does not exist, exiting...")
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
    parser.add_argument("--params", dest="parameters",
                        help="parmaters for the pipeline components")
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    pipeline = Pipeline(args.PIPELINE, args.parameters)
    pipeline.run(args.INPUT, args.OUTPUT, args.verbose, args.intermediate)
