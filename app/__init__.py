import os
from curses import flash

from dotenv import load_dotenv
from flask import Flask, redirect, url_for
from flask_login import current_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from requests import session

from core.configuration.configuration import get_app_version
from core.managers.config_manager import ConfigManager
from core.managers.error_handler_manager import ErrorHandlerManager
from core.managers.logging_manager import LoggingManager
from core.managers.module_manager import ModuleManager

load_dotenv()

db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name="development"):
    app = Flask(__name__)

    config_manager = ConfigManager(app)
    config_manager.load_config(config_name=config_name)

    db.init_app(app)
    migrate.init_app(app, db)

    module_manager = ModuleManager(app)
    module_manager.register_modules()

    from flask_login import LoginManager

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        from app.modules.auth.models import User

        return User.query.get(int(user_id))

    logging_manager = LoggingManager(app)
    logging_manager.setup_logging()

    error_handler_manager = ErrorHandlerManager(app)
    error_handler_manager.register_error_handlers()

    @app.before_request
    def check_session_globally():
        from flask import request as flask_request

        if flask_request.endpoint == "static":
            return None
        excluded_paths = [
            "/auth/login",
            "/auth/signup",
            "/auth/verify_2fa",
            "/auth/logout",
            "/auth/check_session",
        ]
        current_path = flask_request.path
        if any(current_path.startswith(path) for path in excluded_paths):
            return None
        if current_user.is_authenticated:
            try:
                from app.modules.auth.services import AuthenticationService

                auth_service = AuthenticationService()
                if not auth_service.is_current_session_valid():
                    logout_user()
                    session.clear()
                    flash("Tu sesión ha sido cerrada desde otro dispositivo.", "warning")
                    return redirect(url_for("auth.login"))
            except Exception as e:
                import traceback

                app.logger.error(f"Error verificando sesión: {str(e)}\n{traceback.format_exc()}")
                logout_user()
                flash("Error validando tu sesión. Por favor, inicia sesión nuevamente.", "warning")
                return redirect(url_for("auth.login"))
        return None

    @app.context_processor
    def inject_vars_into_jinja():
        return {
            "FLASK_APP_NAME": os.getenv("FLASK_APP_NAME"),
            "FLASK_ENV": os.getenv("FLASK_ENV"),
            "DOMAIN": os.getenv("DOMAIN", "localhost"),
            "APP_VERSION": get_app_version(),
        }

    return app


app = create_app()
