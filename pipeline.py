"""pipeline.py

Running a pipeline of CLAMS applications from the command line. Assumes that
appplications are up and running as Fask services and that they were started
using docker-compose.yml. See README.md for more details.

Usage:

$ python3 pipeline.py INPUT_FILE APPLICATION*

The list of applications should be the names of the services as used in the
configuration in docker-compose.yml. It may be empty, in which case a default
list is generated from the config file.

Examples:

$ python pipeline.py example-mmif.json
$ python pipeline.py example-mmif.json tokenizer spacy

The first one runs all the services define in docker-compose.yml ordered on port
number.

"""

import sys
import json
import yaml
from operator import itemgetter

import requests


class Services(object):

    """Holds the names of services and their URLs, where the names and URLs are
    taken from a docker compose configuraiton file."""
    
    def __init__(self, fname):
        """Build a dictionary of service names and their URL."""
        with open(fname, 'r') as fh:
            specs = yaml.safe_load(fh)
        self.services = {}
        services = specs['services']
        for service in services:
            port = services[service]['ports'][0].split(':')[0]
            url = 'http://0.0.0.0:%s/' % port
            self.services[service] = url

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

    def __init__(self, services, pipeline=None):
        self.services = services
        if pipeline is None:
            self.pipeline = self.services.service_names()
        else:
            self.pipeline = pipeline

    def __str__(self):
        return "<Pipeline %s on %s>" % ('|'.join(self.pipeline), self.services)

    def run(self, fname):
        mmif_string = open(fname).read()
        result = None
        step = 0
        for service in self.pipeline:
            print("Running %s" % service)
            step += 1
            input_string = mmif_string if result is None else result
            # not using the metadata at the moment
            # metadata = self.services.metadata(service)
            result = services.run(service, input_string)
            result = input_string if result is None else result
            with open("out-%d-%s.json" % (step, service), 'w') as fh:
                fh.write(result)


if __name__ == '__main__':

    input_file = sys.argv[1]
    pipeline = sys.argv[2:] if len(sys.argv) > 2 else None
    services = Services('docker-compose.yml')
    pipeline = Pipeline(services, pipeline)
    pipeline.run(input_file)
