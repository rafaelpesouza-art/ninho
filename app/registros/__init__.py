from flask import Blueprint

registros_bp = Blueprint("registros", __name__)

from . import routes  # noqa: E402, F401
