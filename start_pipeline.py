"""start_pipeline.py

Script to start a pipeline from a configuration file. Starting a pipeline means
firing up containers for all applications via a docker-compose command as well
as a container for the pipeline code itself. This assumes that images for all
CLAMS applications as well as for this repository are available, so these would
have to be built prior to starting a pipeline.

Use python 3.6 or higher, see requirements.tx for module requirements.

Usage:

$ python start_pipeline.py <config_file>

When running this the following happens:

- <config_file> is read and used to create docker-compose.yml
- "docker-compose up -d" will run to start the containers
- configuration files are saved to the local directory and the pipeline
  container

Use "docker-compose down" to spin down and delete all containers.

See README.md for more details.

"""

import os
import sys
import yaml


def load_config(fname):
    with open(config_file, 'r') as fh:
        specs = yaml.safe_load(fh)
        return specs


def generate_docker_compose(config_file, compose_file):
    cfg = load_config(config_file)
    # I do not know how to control the layout with yaml.dump(), so I am doing
    # this manually
    with open(compose_file, 'w') as fh:
        fh.write("version: '3'\n\n")
        fh.write("services:\n")
        pipeline_image = cfg['pipeline']['image']
        pipeline_container = cfg['pipeline']['container']
        print_service(fh, 'pipeline', pipeline_container, pipeline_image,
                      cfg['data'], pipeline_container=True)
        port = 5000
        for service in cfg['services']:
            port += 1
            # there is only one pair of items in each service
            for service_name, props in service.items():
                container = props['container']
                image = props['image']
                print_service(fh, service_name, container, image, cfg['data'],
                              port=port)


def print_service(fh, name, container, image, data_dir, pipeline_container=False, port=None):
    fh.write('\n  %s:\n' % name)
    fh.write('    container_name: %s\n' % container)
    fh.write('    image: %s\n' % image)
    if pipeline_container:
        fh.write('    stdin_open: true\n')
        fh.write('    tty: true\n')
    fh.write('    volumes:\n')
    fh.write('      - "%s:/data"\n' % data_dir)
    if port is not None:
        fh.write('    ports:\n')
        fh.write('      - "%s:5000"\n' % port)



if __name__ == '__main__':

    config_file = sys.argv[1]
    compose_file = 'docker-compose.yml'
    generate_docker_compose(config_file, compose_file)
    for command in ('cp %s config.yml' % config_file,
                    'docker-compose up -d',
                    'docker cp %s pipeline:/app/config.yml' % config_file,
                    'docker cp %s pipeline:/app/docker-compose.yml' % compose_file):
        print ('$', command)
        os.system(command)
