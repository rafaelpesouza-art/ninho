from flask import Blueprint

configuracoes_bp = Blueprint("configuracoes", __name__)

from . import routes  # noqa: E402, F401
