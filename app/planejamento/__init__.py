from flask import Blueprint

planejamento_bp = Blueprint("planejamento", __name__)

from . import routes  # noqa: E402, F401
