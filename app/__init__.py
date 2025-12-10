import os

from dotenv import load_dotenv
from flask import Flask
from flask_login import current_user, logout_user
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy

from core.configuration.configuration import get_app_version
from core.managers.config_manager import ConfigManager
from core.managers.error_handler_manager import ErrorHandlerManager
from core.managers.logging_manager import LoggingManager
from core.managers.module_manager import ModuleManager

# Load environment variables
load_dotenv()

# Create the instances
db = SQLAlchemy()
migrate = Migrate()


def create_app(config_name="development"):
    app = Flask(__name__)

    # Load configuration according to environment
    config_manager = ConfigManager(app)
    config_manager.load_config(config_name=config_name)

    # Initialize SQLAlchemy and Migrate with the app
    db.init_app(app)
    migrate.init_app(app, db)

    # Register modules
    module_manager = ModuleManager(app)
    module_manager.register_modules()

    # Register login manager
    from flask_login import LoginManager

    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    @login_manager.user_loader
    def load_user(user_id):
        from app.modules.auth.models import User

        return User.query.get(int(user_id))

    # Set up logging
    logging_manager = LoggingManager(app)
    logging_manager.setup_logging()

    # Initialize error handler manager
    error_handler_manager = ErrorHandlerManager(app)
    error_handler_manager.register_error_handlers()

    @app.before_request
    def check_session_globally():
        """
        Verifica en cada petición si la sesión del usuario sigue siendo válida.
        Si la sesión fue cerrada desde otro dispositivo, fuerza logout y redirige al login.
        """
        from flask import flash as flask_flash
        from flask import redirect
        from flask import request as flask_request
        from flask import session as flask_session_object
        from flask import url_for

        NO_CHECK_PATHS = [
            "/auth/",
            "/static/",
            "/public/",
            "/favicon.ico",
            "/logout",
        ]

        current_path = flask_request.path
        for no_check_path in NO_CHECK_PATHS:
            if current_path.startswith(no_check_path):
                return None
        if current_user.is_authenticated:
            try:
                from app.modules.auth.services import AuthenticationService

                auth_service = AuthenticationService()

                if not auth_service.is_current_session_valid():
                    logout_user()
                    flask_session_object.clear()
                    flask_flash("Tu sesión ha sido cerrada desde otro dispositivo.", "warning")
                    return redirect(url_for("auth.login"))

            except Exception as e:
                app.logger.error(f"Error en check_session_globally: {e}")
                logout_user()
                flask_session_object.clear()
                return redirect(url_for("auth.login"))

        return None

    # Injecting environment variables into jinja context
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
