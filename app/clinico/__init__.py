from flask import Blueprint

clinico_bp = Blueprint("clinico", __name__)

from . import routes  # noqa: E402, F401
