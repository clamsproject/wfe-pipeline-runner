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

$ python3 run_pipeline.py [OPTIONS] INPATH OUTPATH [APPLICATION*]

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
  -a, --abort          abort pipeline processing on error
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


# Return status of services with errors, this if for those cases where there is
# an error, but the service itself did not catch and deal with it. 
REQUEST_ERROR = 0    # requests.post() raised a RequestException
PIPELINE_ERROR = -1  # any other error


class Service(object):

    def __init__(self, name, specs, compose_specs, parameters):
        self.name = name
        self.specs = specs
        self.image = specs['image']
        self.container = specs['container']
        self.port = compose_specs['ports'][0].split(':')[0]
        self.url = self._get_url()
        self._metadata = None
        self.parameters = specs.get('parameters', {})
        if isinstance(parameters, str):
            for parameter in parameters.split(','):
                name, value = parameter.split('=')
                component, name = name.split('-', 1)
                if component == self.name:
                    self.parameters[name] = value

    def _get_url(self):
        """Return the url of the service."""
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

    def identifier(self):
        """Return the identifier of the service, which following the metadata fashion of
        the week could be in the 'identifier', 'iri' or 'app' property."""
        metadata = self.metadata()
        for prop in ('identifier', 'iri', 'app'):
            if prop in metadata:
                return metadata[prop]
        return 'no-app-identifier-available'

    def run(self, input_string):
        """Run the service on the input string. Return the response status and
        the response string, return REQUEST_ERROR and the input string if the
        request failed and return PIPELINE_ERROR and the input if some other
        error occurred in the pipeline."""
        try:
            response = requests.post(self.url, data=input_string, params=self.parameters)
            return response.status_code, response.text
        except requests.exceptions.RequestException as e:
            # Just raising the generic request exception, there is no HTTP error code here
            # Could do something more specific for some cases like timeout and others that
            # have an HTTP error code, for all possible exceptions see
            # https://docs.python-requests.org/en/master/_modules/requests/exceptions/
            print("WARNING: RequestException error connecting to %s, returning input MMIF" % url)
            print("WARNING: %s" % e)
            return REQUEST_ERROR, input_string
        except Exception as e:
            print("WARNING: Exception running service, returning input MMIF" % url)
            print("WARNING: %s" % e)
            return PIPELINE_ERROR, input_string


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

    def run(self, in_path, out_path,
            verbose=False, intermediate=False, abort=False):
        self.verbose = verbose
        self.intermediate = intermediate
        self.abort = abort
        if verbose:
            print("\nServices in pipeline:")
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
            for fname in sorted(os.listdir(in_path)):
                infile = os.path.join(in_path, fname)
                outfile = os.path.join(out_path, fname)
                if os.path.isfile(infile):
                    try:
                        print('>>>', infile)
                        self.run_on_file(infile, outfile)
                    except Exception as e:
                        print("WARNING: error on '%s': %s" % (fname, e))

    def run_on_file(self, infile, outfile):
        self.time_elapsed = {}
        mmif_in = open(infile).read()
        if not input_is_valid(mmif_in):
            return
        for (step, service_name) in enumerate(self.pipeline):
            t0 = time.time()
            if self.verbose:
                print("\n... Running %s" % service_name)
            service = self.services_idx[service_name]
            #mmif_in = self._introduce_error(service, 'tokenizer', mmif_in)
            status_code, mmif_out = service.run(mmif_in)
            mmif = get_mmif_object(mmif_out)
            error, error_message = self._check_status(status_code, mmif)
            #print_input_and_output(service, error, error_message, mmif_in, mmif_out)
            # case 1: no error
            if not error:
                pass
            # case 2: there was an error, but the application dealt with it
            elif error_message is None:
                # TODO: may want to add the status_code to the error in the view
                # metadata, or log this to a file
                pass
            # case 3: request error or other error, create mmif with new error view
            else:
                if mmif_out.startswith('<'):
                    # the output from the application is an XML error string
                    error_message = get_error_message_from_xml(mmif_out, error_message)
                    mmif = mmif_with_error_view(mmif_in, service, error_message)
                    mmif_out = str(mmif)
                else:
                    # the output from the application is MMIF
                    mmif = mmif_with_error_view(mmif_in, service, error_message)
                    mmif_out = str(mmif_out)
            self._save_intermediate_file(outfile, step, service_name, mmif_out)
            self.time_elapsed[service.metadata()['identifier']] = time.time() - t0
            if error and error_message is not None and self.verbose:
                print("    ... Warning, error while running application")
                print("    ...", error_message)
            if error and self.abort:
                if self.verbose:
                    print("    ... Aborting with error")
                break
            mmif_in = mmif_out
        self._write_output(outfile, mmif, mmif_out, error)
        if self.verbose:
            self.print_statistics(outfile, mmif_out)

    def _check_status(self, status_code, mmif):
        """Check the status_code and the mmif object and return a boolean indicating
        where an error occurred and a message string, the latter is None if there was
        no error or if the mmif would already have the error string."""
        if status_code == 200 and mmif is not None:
            # all clear, total success
            error = False
            error_message = None
        else:
            error = True
            if 300 <= status_code < 600 and mmif is not None:
                # error reported by the service, but we got a Mmif object
                # no other action needed, error message is in the view
                error_message = None
            elif status_code == REQUEST_ERROR and mmif is not None:
                # request exception, just define an error message
                error_message = "Request Exception when running service from pipeline"
            elif status_code == PIPELINE_ERROR and mmif is not None:
                # some other error when running the service in the pipeline
                error_message = "Unspecified mishap when running service from pipeline"
            else:
                # some other mishap, define an error message
                error_message = "Unspecified mishap in pipeline runner"
        return error, error_message

    def _write_output(self, outfile, mmif, mmif_out, error):
        with open(outfile, 'w') as fh:
            if error:
                # alway use pretty print and the mmif object if there is an error
                fh.write(mmif.serialize(pretty=True))
            else:
                # otherwise just write the mmif string as given
                fh.write(mmif_out)

    def _introduce_error(self, service, failing_service, mmif_string):
        """Debugging code used to introduce an error on purpose by making the MMIF
        string invalid JSON."""
        # edit the value to make a service fail
        failing_service = None
        failing_service = 'tokenizer'
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

    def print_statistics(self, outfile, result):
        print('\nStatistics for each view in "%s"' % outfile)
        for view in Mmif(result).views:
            time_elapsed = self.time_elapsed.get(view.metadata.app, 0.0)
            # TODO: now view.metadata['error'] always evaluates to True, even if
            # there was no error, so we check for the message; update this when
            # behavior of view.metadata changes
            #print('1>>>', type(view.metadata))
            #print('2>>>', view.metadata)
            #if view.metadata.error:
            #    print('3>>>', view.metadata.error)
            if 'message' in view.metadata.error:
                #status = 'status=ERROR - %s' % view.metadata['error']['message']
                status = 'status=ERROR'
            else:
                status = 'status=OKAY - %d annotations' % len(view.annotations)
            print('    %s app=%s time=%.2fs %s'
                  % (view.id, view.metadata.app, time_elapsed, status))
        print()


def input_is_valid(mmif_string):
    try:
        Mmif(mmif_string)
        return True
    except Exception as e:
        print("ERROR: input is not a valid Mmif object -- %s" % str(e).split('\n')[0])
        return False


def get_mmif_object(mmif_string):
    """Return the Mmif object for the string, return None if creating the Mmif
    object fails."""
    try:
        return Mmif(mmif_string)
    except:
        return None
                

def mmif_with_error_view(base_mmif, service, error_message):
    mmif_out = Mmif(base_mmif)
    error_view = mmif_out.new_view()
    error_view.metadata.app = service.identifier()
    error_view.metadata.set_additional_property('error', {'message': error_message})
    return mmif_out


def get_error_message_from_xml(xml, error_message):
    """Pull the error message from the XML. This is only geared towards finding
    the error thrown by the server when there is an illegal parameter."""
    message = error_message
    for line in xml[:400].split("\n"):
        if 'Error' in line:
            fields = line.split('&#x27;')
            if len(fields) > 1:
                message = fields[1]
    return message


def print_input_and_output(service, error, error_message, mmif_in, mmif_out):
    print('-' * 90)
    print('>>>', service); print('>>>', (error, error_message))
    print('-' * 40 , 'mmif_in', '-' * 40); print(mmif_in[:400])
    print('-' * 40 , 'mmif_out', '-' * 40); print(str(mmif_out)[:400]); print('-' * 90)



def error(http_code, service, message, stacktrace):
    # TODO: this is probably deprecated
    return { "http-error": http_code,
             "app": service.metadata().get('iri'),
             "message": message,
             "stacktrace": stacktrace }

                
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
    parser.add_argument("-a", "--abort", action="store_true",
                        help="abort pipeline processing on error")
    parser.add_argument("--params", dest="parameters", default=None,
                        help="parameters for the pipeline components")
    return parser.parse_args()


if __name__ == '__main__':

    args = parse_arguments()
    pipeline = Pipeline(args.PIPELINE, args.parameters)
    pipeline.run(args.INPUT, args.OUTPUT,
                 args.verbose, args.intermediate, args.abort)
