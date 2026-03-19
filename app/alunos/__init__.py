from flask import Blueprint

alunos_bp = Blueprint("alunos", __name__)

from . import routes  # noqa: E402, F401
