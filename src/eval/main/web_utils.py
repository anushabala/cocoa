__author__ = 'anushabala'
from flask import g
from flask import current_app as app

from backend import EvalBackend


def get_backend():
    backend = getattr(g, '_backend', None)
    if backend is None:
        backend = g._backend = EvalBackend(
            app.config["params"],
            app.config["evaluations"]
        )
    return backend
