from flask import Blueprint

comunicacao_bp = Blueprint("comunicacao", __name__)

from . import routes  # noqa: E402, F401
