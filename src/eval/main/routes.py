__author__ = 'anushabala'

import uuid

from flask import jsonify, render_template, request, redirect, url_for, Markup

from flask import current_app as app

from . import main
from src.eval.main.web_utils import get_backend


def generate_userid(prefix="U_"):
    return prefix + uuid.uuid4().hex


def userid():
    return request.args.get('uid')


def userid_prefix():
    return userid()[:6]


def generate_unique_key():
    return str(uuid.uuid4().hex)


@main.route('/index', methods=['GET', 'POST'])
@main.route('/', methods=['GET', 'POST'])
def index():
    """Chat room. The user's name and room must be stored in
    the session."""

    if not request.args.get('uid'):
        prefix = "U_"
        if request.args.get('mturk') and int(request.args.get('mturk')) == 1:
            # link for Turkers
            prefix = "MT_"

        return redirect(url_for('main.index', uid=generate_userid(prefix), **request.args))

    backend = get_backend()
    backend.create_user_if_not_exists(userid())

    mturk = True if request.args.get('mturk') and int(request.args.get('mturk')) == 1 else None
    if backend.is_user_starting(userid()):
        backend.start_user_session(userid())
        return render_template('instructions.html',
                               uid=userid(),
                               evals_per_worker=app.config['params']['evals_per_worker'])
    elif backend.is_user_finished(userid()):
        # show completion code
        code = backend.generate_code(userid()) if mturk else None
        return render_template('finished.html',
                               uid=userid(),
                               evals_per_worker=app.config['params']['evals_per_worker'],
                               mturk_code=code)
    else:
        evaluation = backend.get_next_evaluation(userid())
        task_num = backend.get_task_num(userid())
        return render_template('eval_task.html',
                               uid=userid(),
                               eval_num=task_num,
                               evals_per_worker=app.config['params']['evals_per_worker'],
                               evaluation=evaluation,
                               attributes=evaluation['kb']['item'].keys())


@main.route('/_submit/', methods=['POST'])
def submit():
    backend = get_backend()
    response = request.json['response']
    uid = request.json['uid']
    ex_id = request.json['evaluation_id']

    backend.submit(uid, ex_id, response)
    return jsonify(success=True)

