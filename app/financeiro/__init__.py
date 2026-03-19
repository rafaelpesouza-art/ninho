from flask import Blueprint

financeiro_bp = Blueprint("financeiro", __name__)

from . import routes  # noqa: E402, F401
