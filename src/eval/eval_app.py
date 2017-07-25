import argparse
import json
import sqlite3
from datetime import datetime
import os
import shutil
import atexit

from src.eval import create_app
from gevent.pywsgi import WSGIServer
from src.eval.main.web_logger import WebLogger
from src.eval.process_evals import process_evaluations

__author__ = 'anushabala'

DB_FILE_NAME = 'web_state.db'
LOG_FILE_NAME = 'log.out'
ERROR_LOG_FILE_NAME = 'error_log.out'
TRANSCRIPTS_DIR = 'results'


def add_website_arguments(parser):
    parser.add_argument('--port', type=int, default=5000,
                        help='Port to start server on')
    parser.add_argument('--host', type=str, default='127.0.0.1',
                        help='Host IP address to run app on. Defaults to localhost.')
    parser.add_argument('--eval-file', type=str, required=True,
                        help='File containing candidates for evaluation')
    parser.add_argument('--config', type=str, required=True,
                        help='File containing configurations for website')
    parser.add_argument('--output', type=str,
                        default="eval_output/{}".format(datetime.now().strftime("%Y-%m-%d")),
                        help='Name of directory for storing website output (debug and error logs, chats, '
                             'and database). Defaults to a web_output/current_date, with the current date formatted as '
                             '%%Y-%%m-%%d. '
                             'If the provided directory exists, all data in it is overwritten unless the '
                             '--reuse parameter is provided.')
    parser.add_argument('--reuse', action='store_true', help='If provided, reuse and don\'t overwrite the '
                                                             'output directory.')


def init_database(db_file):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute(
        '''CREATE TABLE active_user (userid text unique, evaluated integer, skipped text, created_at text)'''
    )
    c.execute(
        '''CREATE TABLE completion_code (userid text, code text, submitted_at text)'''
    )
    c.execute(
        '''CREATE TABLE evaluation (id text unique, active text, completed text)'''
    )
    c.execute(
        '''CREATE TABLE response (userid text, id text, response text)'''
    )
    c.execute(
        '''CREATE TABLE assigned_eval (userid text, id text, timestamp text)'''
    )

    conn.commit()
    conn.close()


def add_evaluations_to_db(db_file, evaluations, update=False):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    for uuid in evaluations.keys():
        if update:
            c.execute('''INSERT OR IGNORE INTO evaluation VALUES (?,"[]","[]")''', (uuid,))
        else:
            c.execute('''INSERT INTO evaluation VALUES (?,"[]","[]")''', (uuid,))

    conn.commit()
    conn.close()


def dump_results(evaluations, db_path, transcript_path):
    responses = {}
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute('''SELECT * FROM response''')
    for userid, exid, r in cursor.fetchall():
        if exid not in responses:
            responses[exid] = []
        r = json.loads(r)
        r = [int(x) for x in r]
        responses[exid].append(r)

    results = []
    for exid in responses.keys():
        e = evaluations[exid]
        e['results'] = responses[exid]
        results.append(e)

    json.dump(results, open(transcript_path, 'w'))


def cleanup(flask_app):
    db_path = flask_app.config['params']['db']['location']
    transcript_path = os.path.join(flask_app.config['params']['logging']['results_dir'], 'eval_results.json')
    evaluations = flask_app.config['evaluations']
    dump_results(evaluations, db_path, transcript_path)


def init(output_dir, reuse=False):
    db_path = os.path.join(output_dir, DB_FILE_NAME)
    log_path = os.path.join(output_dir, LOG_FILE_NAME)
    error_log_path = os.path.join(output_dir, ERROR_LOG_FILE_NAME)
    results_path = os.path.join(output_dir, TRANSCRIPTS_DIR)

    if not reuse:
        if os.path.exists(output_dir):
            shutil.rmtree(output_dir)
        os.makedirs(output_dir)

        init_database(db_path)

        if os.path.exists(results_path):
            shutil.rmtree(results_path)
        os.makedirs(results_path)

    return db_path, log_path, error_log_path, results_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_website_arguments(parser)
    args = parser.parse_args()

    config_file = args.config
    with open(config_file) as fin:
        params = json.load(fin)

    eval_file = args.eval_file
    evaluations = process_evaluations(eval_file, params)
    print "Processed {:d} evaluation contexts.".format(len(evaluations))
    evaluations = dict((x["exid"], x) for x in evaluations)

    db_file, log_file, error_log_file, results_dir = init(args.output, args.reuse)
    add_evaluations_to_db(db_file, evaluations, update=args.reuse)
    error_log_file = open(error_log_file, 'w')

    WebLogger.initialize(log_file)
    params['db'] = {}
    params['db']['location'] = db_file
    params['logging'] = {}
    params['logging']['app_log'] = log_file
    params['logging']['results_dir'] = results_dir

    instructions = None

    templates_dir = None
    if 'templates_dir' in params.keys():
        templates_dir = params['templates_dir']
    else:
        raise ValueError("Location of HTML templates should be specified in config with the key templates_dir")
    if not os.path.exists(templates_dir):
            raise ValueError("Specified HTML template location doesn't exist: %s" % templates_dir)

    if 'evals_per_worker' not in params.keys():
        params['evals_per_worker'] = 5

    if 'workers_per_eval' not in params.keys():
        params['workers_per_eval'] = 3

    if 'eval_timeout' not in params.keys():
        params['eval_timeout'] = 600

    app = create_app(debug=False, templates_dir=templates_dir)

    app.config['evaluations'] = evaluations
    app.config['params'] = params

    print "App setup complete"

    server = WSGIServer(('', args.port), app, log=WebLogger.get_logger(), error_log=error_log_file)
    # todo cleanup - dump evals?
    atexit.register(cleanup, flask_app=app)
    server.serve_forever()
