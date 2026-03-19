from flask import Flask
from .extensions import init_supabase
from .auth import auth_bp
from .main import main_bp
from .alunos import alunos_bp
from .agenda import agenda_bp
from .registros import registros_bp
from .financeiro import financeiro_bp
from .comunicacao import comunicacao_bp
from .planejamento import planejamento_bp
from postgrest.exceptions import APIError
from flask import redirect, url_for, flash, session


def create_app(config_object="config.Config"):
    app = Flask(__name__, template_folder="../templates")
    app.config.from_object(config_object)

    # Inicializa extensões
    init_supabase(app)

    # Registra blueprints
    app.register_blueprint(auth_bp, url_prefix="/auth")
    app.register_blueprint(main_bp)
    app.register_blueprint(alunos_bp, url_prefix="/alunos")
    app.register_blueprint(agenda_bp, url_prefix="/agenda")
    app.register_blueprint(registros_bp, url_prefix="/registros")
    app.register_blueprint(financeiro_bp, url_prefix="/financeiro")
    app.register_blueprint(comunicacao_bp, url_prefix="/comunicacao")
    app.register_blueprint(planejamento_bp, url_prefix="/planejamento")
    @app.errorhandler(APIError)
    def handle_api_error(error):
        # PGRST303 é o código de erro do Supabase/PostgREST para JWT expirado ou inválido
        if hasattr(error, 'code') and error.code == 'PGRST303' or getattr(error, 'message', '') == 'JWT expired':
            session.clear()
            flash("Sua sessão expirou. Por favor, faça login novamente.", "warning")
            return redirect(url_for('auth.login_page'))
        # Repassa o erro se não for JWT expirado (já que o debug_toolbar ou app pode lidar)
        raise error

    return app
