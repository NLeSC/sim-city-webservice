# SIM-CITY webservice
#
# Copyright 2015 Netherlands eScience Center
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

#
# This file implements a mock version of the normal webservice
#
import bottle
from bottle import (post, get, run, delete, request, response, HTTPResponse,
                    static_file, hook)
from simcity import parse_parameters
from simcity.util import listfiles
from simcityweb.util import SimulationConfig
from simcityweb import error
from uuid import uuid4
import os
import json
import accept_types

prefix = '/explore'

# Get project directory
file_dir = os.path.dirname(os.path.realpath(__file__))
project_dir = os.path.dirname(file_dir)

config_sim = {'max_jobs': 1}
config_hosts = {}

# Mock database using a dictionary
mock_db = dict()


# Load a json file with pre made test tasks
def load_pre_made_tasks():
    for _root, dirs, files in os.walk('mock_tasks', topdown=False):
        for name in files:
            if name.endswith('.json'):
                filename = os.path.join(_root, name)
                with open(filename) as _file:
                    task = json.load(_file)
                    mock_db[task['id']] = task


# WARNING:
# Loading the json file in this manner probably means
# it is loaded for every request so we shouldn't make too many
load_pre_made_tasks()

# Remove spaces from json output
bottle.uninstall('json')
bottle.install(bottle.JSONPlugin(
    json_dumps=lambda x: json.dumps(x, separators=(',', ':'))))


# Remove trailing / from request
@hook('before_request')
def strip_path():
    request.environ['PATH_INFO'] = request.environ['PATH_INFO'].rstrip('/')


@get(prefix)
def root():
    doc_dir = os.path.join(project_dir, 'docs')
    return static_file('swagger.json', mimetype='application/json',
                       root=doc_dir)


@get(prefix + '/doc')
def get_doc():
    docs = [
        ('text/html', 'apiary.html'),
        ('application/json', 'swagger.json'),
        ('text/markdown', 'apiary.apib'),
    ]
    accept = accept_types.get_best_match(
        request.headers.get('Accept'), [t[0] for t in docs])

    if accept is None:
        return error(406, "documentation {0} not found. choose between {1}"
                     .format(accept, [t[0] for t in docs]))

    doc_dir = os.path.join(project_dir, 'docs')
    return static_file(dict(docs)[accept], mimetype=accept, root=doc_dir)


@get(prefix + '/simulate')
def simulate_list():
    simulations = {}
    try:
        for f in listfiles('simulations'):
            if not (f.endswith('.yaml') or f.endswith('.json')) \
               or f.endswith('.min.json'):
                continue

            name = f[:-5]
            config = SimulationConfig(name, 'simulations')
            simulations[name] = {
                'name': name,
                'versions': config.get_versions()
            }

        return simulations
    except HTTPResponse as ex:
        return ex


@get(prefix + '/simulate/<name>')
def get_simulation_by_name(name):
    try:
        response.status = 200
        config = SimulationConfig(name, 'simulations')
        return {'name': name, 'versions': config.get_versions()}
    except HTTPResponse as ex:
        return ex


@get(prefix + '/simulate/<name>/<version>')
def get_simulation_by_name_version(name, version=None):
    try:
        config = SimulationConfig(name, 'simulations')
        sim = config.get_simulation(version)
        chosen_sim = sim.description
        chosen_sim['name'] = sim.name
        chosen_sim['version'] = sim.version
        response.status = 200
        return chosen_sim
    except HTTPResponse as ex:
        return ex


@post(prefix + '/simulate/<name>')
def simulate_name(name):
    return simulate_name_version(name)


@post(prefix + '/simulate/<name>/<version>')
def simulate_name_version(name, version=None):
    if not hasattr(simulate_name_version, 'nextId'):
        # Initialize static variable
        simulate_name_version.nextId = 0

    try:
        query = dict(request.json)
    except TypeError:
        return error(412, "request must contain json input")

    if '_id' in query:
        task_id = query['_id']
        del query['_id']
    else:
        task_id = str(simulate_name_version.nextId)
        simulate_name_version.nextId += 1

    try:
        config = SimulationConfig(name, 'simulations')
        sim = config.get_simulation(version)
        sim = sim.description
        sim['type'] = 'object'
        sim['additionalProperties'] = False
        parse_parameters(query, sim)
    except HTTPResponse as ex:
        return ex
    except ValueError as ex:
        return error(412, str(ex))
    except EnvironmentError as ex:
        return error(500, ex.message)

    # Create the response we would normally get from
    # the database
    task_props = {
        'id': task_id,
        'key': task_id,
        'value': {
            '_id': task_id,
            '_rev': uuid4().hex,
            'lock': 0,
            'done': 0,
            'name': name,
            'command': sim['command'],
            'arguments': sim.get('arguments', []),
            'parallelism': sim.get('parallelism', '*'),
            'version': version,
            'input': query,
            'uploads': {},
            'error': []
        }
    }

    if 'ensemble' in query:
        task_props['ensemble'] = query['ensemble']
    if 'simulation' in query:
        task_props['simulation'] = query['simulation']

    if task_id in mock_db:
        return error(409, "simulation name " + task_id + " already taken")

    # Add the new task to the "database"
    mock_db[task_id] = task_props

    response.status = 201  # created

    # Normally we return a link to the database, but now
    # we point to sim-city-webservice
    host = bottle.request.get_header('host')
    url = '%s/task/%s' % (host, task_id)
    response.set_header('Location', url)
    return task_props


@get(prefix + '/schema')
def schema_list():
    files = listfiles('schemas')
    return {'schemas': [f[:-5] for f in files if f.endswith('.json')]}


@get(prefix + '/schema/<name>')
def schema_name(name):
    return static_file(os.path.join('schemas', name + '.json'),
                       root=project_dir, mimetype='application/json')


@get(prefix + '/resource')
def resource_list():
    files = listfiles('resources')
    return {"resources": [f[:-5] for f in files if f.endswith('.json')]}


@get(prefix + '/resource/<name>')
def resource_name(name):
    return static_file(os.path.join('resources', name + '.json'),
                       root=project_dir, mimetype='application/json')


@get(prefix + '/view/totals')
def overview():
    try:
        return mock_overview_total()
    except:
        return error(500, "cannot read overview")


def mock_overview_total():
    views = ['pending', 'in_progress', 'error', 'done', 'unknown',
             'finished_jobs', 'active_jobs', 'pending_jobs']

    num = dict((view, 0) for view in views)

    for key, task in mock_db.items():
        val = task['value']
        if val['done'] > 0:
            num['done'] += 1
        elif val['in_progress'] > 0:
            num['in_progress'] += 1
        elif val['lock'] == 0:
            num['todo'] += 1
        elif val['lock'] == -1:
            num['error'] += 1
        else:
            num['unknown'] += 1

    return num


@post(prefix + '/job')
def submit_job():
    if not hasattr(submit_job, 'batch_id'):
        submit_job.batch_id = 1

    # Mock the response for submitting the job
    host = config_sim['default_host']
    _prefix = host + '-'
    batch_id = str(submit_job.batch_id)
    submit_job.batch_id += 1
    job_id = 'job_' + _prefix + uuid4().hex

    response.status = 201  # created
    return {'_id': job_id, 'batch_id': batch_id, 'hostname': host}


@get(prefix + '/simulation/<_id>')
def get_simulation(_id):
    if _id in mock_db:
        return mock_db[_id]['value']
    else:
        return error(404, "simulation does not exist")


@get(prefix + '/view/simulations/<name>/<version>')
def simulations_view(name, version):
    ensemble = request.query.get('ensemble')
    config = SimulationConfig(name, 'simulations')
    sim = config.get_simulation(version)
    version = sim.version

    simulations = [task for k, task in mock_db.items() if
                   task['value']['name'] == name and
                   task['value']['version'] == version and
                   (ensemble is None or task['value']['ensemble'] == ensemble)]

    response.status = 200
    return {'total_rows': len(simulations), 'offset': 0, 'rows': simulations}


@get(prefix + '/simulation/<id>/<attachment>')
def get_attachment(id, attachment):
    return static_file(os.path.join('mock_results', attachment),
                       root=project_dir)


@delete(prefix + '/simulation/<_id>')
def del_simulation(_id):
    rev = request.query.get('rev')
    if rev is None:
        rev = request.get_header('If-Match')
    if rev is None:
        return error(409, "revision not specified")

    if _id in mock_db:
        task = mock_db[_id]
        if task['value']['_rev'] == rev:
            del mock_db[_id]
            return {'ok': True}
        else:
            return error(409, "resource conflict")
    else:
        return error(404, "Resource does not exist")


@get(prefix + '/hosts')
def get_hosts():
    return config_hosts


if __name__ == '__main__':
    run(host='localhost', port=9090, server='wsgiref')
