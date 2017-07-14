import argparse
from collections import defaultdict
import json
import sqlite3
from datetime import datetime
import os
import shutil
import string
import warnings
import atexit
from flask import Markup

from src.basic.util import read_json
from src.eval import create_app
from gevent.pywsgi import WSGIServer
from src.eval.main.web_logger import WebLogger

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


def init_database(db_file):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    c.execute(
        '''CREATE TABLE active_user (userid text unique, evaluated integer, created_at text)'''
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


def add_evaluations_to_db(db_file, evaluations):
    conn = sqlite3.connect(db_file)
    c = conn.cursor()
    for uuid in evaluations.keys():
        c.execute('''INSERT INTO evaluation VALUES (?,"[]","[]")''', (uuid,))

    conn.commit()
    conn.close()


def preprocess_utterance(tokens):
    s = ""
    for (idx, token) in enumerate(tokens):
        if isinstance(token, str) or isinstance(token, unicode):
            if token == "</s>":
                if idx != len(tokens) - 1:
                    token = "<br>"
                else:
                    token = ""
            elif token == "_start_":
                token = "START"
            elif token.startswith("<") and token.endswith(">"):
                token = token.upper().strip("<").strip(">")
            if token not in string.punctuation and not token.startswith("'") and not "'" in token:
                s += " " + token
            else:
                s += token
        elif isinstance(token, list):
            if token[1][1] == 'price':
                s += " " + "PRICE"
            else:
                s += " " + token[0]
    s = s.strip()
    if s == "<br>":
        s = ""
    return Markup(s)


def process_evaluations(eval_file):
    raw_evals = json.load(open(eval_file, 'r'))
    processed = []

    for e in raw_evals:
        if 'exid' not in e or 'prev_roles' not in e:
            continue
        if e['candidates'] is None:
            continue
        candidates = []
        for c in e['candidates']:
            if 'response' not in c.keys():
                continue
            c['response'] = preprocess_utterance(c['response'])
            candidates.append(c)
        e['candidates'] = candidates

        prev_turns = e['prev_turns']
        if len(prev_turns) == 1 and prev_turns[0][0] == '</s>':
            # start of dialogue
            e['prev_turns'] = ['START']
            processed.append(e)
            continue

        processed_turns = []
        for turn in prev_turns:
            processed_turns.append(preprocess_utterance(turn))

        if len(processed_turns[0]) == 0:
            processed_turns.pop(0)
            e['prev_roles'] = e['prev_roles'][1:]

        if len(processed_turns) > params["max_prev_turns"]:
            processed_turns = processed_turns[len(processed_turns)-params["max_prev_turns"]:]
            e['prev_roles'] = e['prev_roles'][len(processed_turns)-params["max_prev_turns"]:]
        e['prev_turns'] = processed_turns

        processed.append(e)

    return processed


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

def init(output_dir):
    db_file = os.path.join(output_dir, DB_FILE_NAME)
    log_file = os.path.join(output_dir, LOG_FILE_NAME)
    error_log_file = os.path.join(output_dir, ERROR_LOG_FILE_NAME)
    results_dir = os.path.join(output_dir, TRANSCRIPTS_DIR)
    if os.path.exists(output_dir):
        shutil.rmtree(output_dir)
    os.makedirs(output_dir)

    init_database(db_file)

    if os.path.exists(results_dir):
        shutil.rmtree(results_dir)
    os.makedirs(results_dir)

    return db_file, log_file, error_log_file, results_dir


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    add_website_arguments(parser)
    args = parser.parse_args()

    config_file = args.config
    with open(config_file) as fin:
        params = json.load(fin)

    eval_file = args.eval_file
    evaluations = process_evaluations(eval_file)
    evaluations = dict((x["exid"], x) for x in evaluations)

    db_file, log_file, error_log_file, results_dir = init(args.output)
    error_log_file = open(error_log_file, 'w')

    WebLogger.initialize(log_file)
    params['db'] = {}
    params['db']['location'] = db_file
    params['logging'] = {}
    params['logging']['app_log'] = log_file
    params['logging']['results_dir'] = results_dir
    add_evaluations_to_db(db_file, evaluations)

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
