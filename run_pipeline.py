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
config file.

Examples:

$ python run_pipeline.py examples/mmif/tokenizer-spacy-1.json out.json
$ python run_pipeline.py examples/mmiftokenizer-spacy-1.json out.json tokenizer spacy

OPTIONS:
  -h, --help           show this help message and exit
  -v, --verbose        print progress to standard output
  -i, --intermediate   save intermediate files
  --params PARAMETERS  parameters for the pipeline components

See README.md for more details, including on the --params option.

"""

import os, sys, shutil, time
import json, yaml
import requests
import argparse
from operator import itemgetter

from mmif import Mmif


# configuration files
CONFIG_FILE = 'config.yml'
COMPOSE_FILE = 'docker-compose.yml'


class Service(object):

    def __init__(self, name, specs, compose_specs, parameters):
        self.name = name
        self.specs = specs
        self.image = specs['image']
        self.container = specs['container']
        self.port = compose_specs['ports'][0].split(':')[0]
        self.url = self._get_url()
        self._metadata = None
        # TODO: the following is likely more complicated than it need be
        parameters = specs.get('parameters')
        if parameters is None:
            self.parameters = {}
        elif isinstance(parameters, str):
            self.parameters = {}
            for parameter in parameters.split(','):
                name, value = parameter.split('=')
                component, name = name.split('-', 1)
                self.parameters[name] = value
        elif isinstance(parameters, dict):
            self.parameters = parameters

    def _get_url(self):
        # The URL depends on whether the pipeline service runs in a container,
        # so we check whether we are in host mode and set the URL accordingly.
        if host_mode():
            return 'http://0.0.0.0:%s/' % self.port
        else:
            return 'http://%s:5000/' % self.specs['container']

    def __str__(self):
        params = ' '.join(["%s=%s" % (k,v) for k,v in self.parameters.items()])
        return "<Service %s %s %s %s>" % (self.name, self.container, self.url, params)

    def metadata(self):
        if self._metadata is None:
            try:
                response = requests.get(self.url)
                self._metadata = json.loads(response.text)
            except requests.exceptions.ConnectionError as e:
                print(">>> WARNING: error connecting to %s, returning empty metadata" % url)
                self._metadata = {}
        return self._metadata

    def run(self, input_string):
        try:
            response = requests.put(self.url, data=input_string, params=self.parameters)
            return response.text
        except requests.exceptions.ConnectionError as e:
            print(">>> WARNING: error connecting to %s, returning input MMIF" % url)
            return input_string


class Pipeline(object):

    """To create a pipeline you first collect all services from the two
    configuration files and then set the pipeline, generate the pipeline from
    the configuration if the pipeline handed in is the empty list."""

    def __init__(self, pipeline, parameters=None):
        with open(COMPOSE_FILE, 'r') as fh1, open(CONFIG_FILE, 'r') as fh2:
            compose_specs = yaml.safe_load(fh1)
            config_specs = yaml.safe_load(fh2)
        self.services = []
        self.services_idx = {}
        # Build a dictionary of service names and their URLs
        for service in config_specs['services']:
            name, service_specs = list(service.items())[0]
            service_compose_specs = compose_specs['services'][name]
            s = Service(name, service_specs, service_compose_specs, parameters)
            self.services.append(s)
            self.services_idx[name] = s
        self.service_names = [s.name for s in self.services]
        self.pipeline = pipeline if pipeline else self.service_names

    def __str__(self):
        return "<Pipeline %s>" % ('|'.join(self.pipeline))

    def run(self, in_path, out_path, verbose=False, intermediate=False):
        self.verbose = verbose
        self.intermediate = intermediate
        if verbose:
            print("Services in pipeline:")
            for service_name in self.pipeline:
                print('   ', self.services_idx[service_name])
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
        self.time_elapsed = {}
        mmif_in = open(infile).read()
        for (step, service_name) in enumerate(self.pipeline):
            t0 = time.time()
            if self.verbose:
                print("...running %s" % service_name)
            service = self.services_idx[service_name]
            mmif_out = self.run_service_on_file(service, mmif_in)
            self._save_intermediate_file(outfile, step, service_name, mmif_out)
            self.time_elapsed[service.metadata()['app']] = time.time() - t0
            mmif_in = mmif_out
        with open(outfile, 'w') as fh:
            fh.write(mmif_out)
        if self.verbose:
            self.print_statistics(infile, mmif_out)

    def run_service_on_file(self, service, mmif_in):
        """Run the service on the mmif input and create mmif output. The output
        has a new view with either an error in the metadata or a dictionary of
        annotation types potentially added by the service."""
        mmif_out = service.run(self._introduce_error(service, mmif_in))
        try:
            # NOTE: this makes sure the result is JSON
            # TODO: should perhaps do this with Mmif(mmif_out)
            json.loads(mmif_out)
            return mmif_out
        except ValueError:
            # TODO. This assumes the error is in the string returned by the
            # service, which will change soon.
            error_message = mmif_out.split('\n')[-2]
            error = { "message": error_message, "stackTrace": mmif_out }
            mmif_out = Mmif(mmif_in)
            error_view = mmif_out.new_view()
            error_view.metadata.app = service.metadata()['app']
            error_view.metadata.set_additional_property('error', error)
            return mmif_out.serialize(pretty=True)

    def _introduce_error(self, service, mmif_string):
        """Debugging code used to introduce an error on purpose by making the MMIF
        string invalid JSON."""
        # edit the value to make a service fail
        failing_service = None
        #failing_service = 'spacy'
        if service.name == failing_service:
            mmif_string += "SCREWING_UP_THE_JSON_SYNTAX"
        return mmif_string

    def _dribble_mmif(self, prefix, mmif, nl=True):
        print(prefix, type(mmif))
        print(prefix, str(mmif)[:80], '...')
        print(prefix, ' ...', str(mmif)[-80:])
        if nl:
            print()

    def _save_intermediate_file(self, outfile, step, service_name, mmif_out):
        if self.intermediate:
            out = outfile[:-5] if outfile.endswith('.json') else outfile
            with open("%s-%d-%s.json" % (out, step + 1, service_name), 'w') as fh:
                fh.write(mmif_out)

    def print_statistics(self, infile, result):
        # TODO: update this for when we have errors
        print
        print('Statistics for each view')
        for view in Mmif(result).views:
            time_elapsed = self.time_elapsed.get(view.metadata.app, 0.0)
            if 'error' in view.metadata:
                status = 'status=ERROR - %s' % view.metadata['error']['message']
            else:
                status = 'status=OKAY - %d annotations' % len(view.annotations)
            print('%s app=%s time=%.2fs %s'
                  % (view.id, view.metadata.app, time_elapsed, status))


def host_mode():
    """Returns True if a 'docker' executable is present; false otherwise. This
    is a simple heuristic to determine if we are running in a container or not,
    assuming that the 'docker' command WILL NOT be present when we are inside a
    container and WILL be present if we are on the host."""
    # NOTE: some suggest to check for the presence of the /.dockerenv file
    # NOTE: maybe use a command line option to distinguish between the two cases
    return shutil.which('docker') is not None


def parse_arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("INPUT", help="the input file or directory")
    parser.add_argument("OUTPUT", help="the output file or directory")
    parser.add_argument("PIPELINE", nargs='*', help="optional pipeline elements")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="print progress to standard output")
    parser.add_argument("-i", "--intermediate", action="store_true",
                        help="save intermediate files")
    parser.add_argument("--params", dest="parameters", default='',
                        help="parameters for the pipeline components")
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    pipeline = Pipeline(args.PIPELINE, args.parameters)
    pipeline.run(args.INPUT, args.OUTPUT, args.verbose, args.intermediate)
