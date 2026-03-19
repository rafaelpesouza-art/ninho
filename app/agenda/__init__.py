from flask import Blueprint

agenda_bp = Blueprint("agenda", __name__)

from . import routes  # noqa: E402, F401
