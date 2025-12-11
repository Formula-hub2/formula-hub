import os
from functools import wraps

from flask import current_app
from flask import flash
from flask import flash as flask_flash_func
from flask import make_response, redirect, render_template, request
from flask import session
from flask import session as flask_session_obj
from flask import url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_user, logout_user
from flask_wtf.csrf import generate_csrf

from app.modules.auth import auth_bp
from app.modules.auth.forms import LoginForm, SignupForm
from app.modules.auth.models import User
from app.modules.auth.services import AuthenticationService
from app.modules.profile.services import UserProfileService

limiter = Limiter(
    key_func=get_remote_address,
    storage_uri=os.environ.get("FLASK_RATELIMIT_STORAGE_URI", "memory://"),
)

authentication_service = AuthenticationService()
user_profile_service = UserProfileService()


# Global check: ensure that any request from an authenticated user belongs to a
# still-valid UserSession. If the DB row was removed (remote logout), force a
# server-side logout and return a response that clears the remember cookie so
# the client won't be auto-logged-in again. This runs before every request and
# covers routes that aren't decorated with `require_valid_session`.
@auth_bp.before_app_request
def ensure_session_is_valid():
    # Only act for authenticated users
    try:
        if not current_user.is_authenticated:
            return None

        # Avoid interfering with auth endpoints themselves or static files
        endpoint = None
        try:
            endpoint = request.endpoint
        except Exception:
            endpoint = None

        exempt_endpoints = {
            "auth.login",
            "auth.logout",
            "auth.verify_2fa",
            "auth.check_session",
            "auth.show_signup_form",
        }
        # Only skip for auth endpoints and static files. Do NOT skip public
        # endpoints: we must validate sessions even when the user requests the
        # main page so we can force a logout+redirect there.
        if endpoint is not None and (endpoint in exempt_endpoints or endpoint.startswith("static")):
            return None

        if not authentication_service.is_current_session_valid():
            current_app.logger.info(
                "Detected invalid session for user=%s, forcing logout", getattr(current_user, "id", None)
            )
            # server-side logout and clear
            logout_user()
            session.clear()
            flask_flash_func("Tu sesión ha sido cerrada desde otro dispositivo.", "warning")
            # Build a response that clears the remember cookie on the client and
            # redirects to the public index (main page) as requested by product
            # behaviour.
            # Redirect to the login page (exempt from validation) to avoid
            # triggering this same handler again and creating redirect loops.
            resp = make_response(redirect(url_for("auth.login")))
            remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
            # Ensure we clear cookie with same path/domain as login manager uses
            resp.delete_cookie(
                remember_cookie_name,
                path=current_app.config.get("REMEMBER_COOKIE_PATH", "/"),
                domain=current_app.config.get("REMEMBER_COOKIE_DOMAIN"),
            )
            return resp
    except Exception:
        # On any error while validating the session, be conservative: logout
        # and force the client to a non-authenticated state.
        try:
            logout_user()
            session.clear()
        except Exception:
            pass
        resp = make_response(redirect(url_for("auth.login")))
        remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
        resp.delete_cookie(
            remember_cookie_name,
            path=current_app.config.get("REMEMBER_COOKIE_PATH", "/"),
            domain=current_app.config.get("REMEMBER_COOKIE_DOMAIN"),
        )
        return resp


def require_valid_session(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if current_user.is_authenticated:
            try:
                if not authentication_service.is_current_session_valid():
                    logout_user()
                    flask_session_obj.clear()
                    flask_flash_func("Tu sesión ha sido cerrada desde otro dispositivo.", "warning")
                    # Build a response so we can ensure the remember cookie is removed on the client
                    resp = make_response(redirect(url_for("auth.login")))
                    remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
                    resp.delete_cookie(remember_cookie_name)
                    return resp
            except Exception:
                logout_user()
                flask_session_obj.clear()
                flask_flash_func("Error validando tu sesión. Por favor, inicia sesión nuevamente.", "warning")
                resp = make_response(redirect(url_for("auth.login")))
                remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
                resp.delete_cookie(remember_cookie_name)
                return resp
        return f(*args, **kwargs)

    return decorated_function


@auth_bp.route("/signup/", methods=["GET", "POST"])
def show_signup_form():
    if current_user.is_authenticated:
        return redirect(url_for("public.index"))

    form = SignupForm()
    if form.validate_on_submit():
        email = form.email.data
        if not authentication_service.is_email_available(email):
            return render_template("auth/signup_form.html", form=form, error=f"Email {email} in use")

        try:
            user = authentication_service.create_with_profile(**form.data)
        except Exception as exc:
            return render_template("auth/signup_form.html", form=form, error=f"Error creating user: {exc}")

        login_user(user, remember=True)
        # Create a corresponding UserSession so subsequent requests (e.g. the
        # redirect to public.index) are considered valid by
        # is_current_session_valid(). This mirrors the behavior in the
        # `login` route.
        try:
            user_session = authentication_service.create_user_session(user)
            session["session_id"] = user_session.session_id
        except Exception:
            # If session creation fails, continue with login but be defensive
            # — the before_request will handle invalid sessions and force a
            # logout if necessary.
            pass

        # Ensure device_id cookie is set for this new signup session so the
        # session will be grouped with subsequent logins from the same browser.
        device_id = request.cookies.get("device_id")
        if not device_id:
            import uuid

            device_id = str(uuid.uuid4())
        resp = make_response(redirect(url_for("public.index")))
        resp.set_cookie("device_id", device_id, max_age=60 * 60 * 24 * 365 * 2, httponly=True, secure=True)
        return resp

    return render_template("auth/signup_form.html", form=form)


@auth_bp.route("/login", methods=["GET", "POST"])
@limiter.limit("5 per minute")
def login():
    if current_user.is_authenticated:
        return redirect(url_for("public.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = authentication_service.get_user_by_email(form.email.data)

        if not user:
            return render_template("auth/login_form.html", form=form, error="Invalid credentials")

        if user and authentication_service.repository.is_account_blocked(user):
            remaining_seconds = authentication_service.get_remaining_seconds(user)
            return (
                render_template(
                    "auth/login_form.html",
                    form=form,
                    countdown=remaining_seconds,
                    error="Demasiados intentos fallidos. Cuenta bloqueada.",
                ),
                429,
            )

        if user and authentication_service.verify_password(user, form.password.data):
            if getattr(user, "two_factor_enabled", False):
                session["two_factor_user_id"] = user.id
                logout_user()
                return redirect(url_for("auth.verify_2fa"))
            device_id = request.cookies.get("device_id")
            if not device_id:
                import uuid

                device_id = str(uuid.uuid4())
            login_user(user, remember=True)
            authentication_service.repository.reset_failed_attempts(user)
            user_session = authentication_service.create_user_session(user)
            session["session_id"] = user_session.session_id
            resp = make_response(redirect(url_for("public.index")))
            resp.set_cookie(
                "device_id",
                device_id,
                max_age=60 * 60 * 24 * 365 * 2,
                httponly=True,
                secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
            )
            return resp
        authentication_service.repository.register_failed_attempt(user)
        if user and authentication_service.repository.is_account_blocked(user):
            remaining_seconds = authentication_service.get_remaining_seconds(user)
            return (
                render_template(
                    "auth/login_form.html",
                    form=form,
                    countdown=remaining_seconds,
                    error="Demasiados intentos fallidos. Cuenta bloqueada.",
                ),
                429,
            )

        return render_template("auth/login_form.html", form=form, error="Invalid credentials")

    return render_template("auth/login_form.html", form=form)


@auth_bp.route("/verify_2fa", methods=["GET", "POST"])
def verify_2fa():
    if "two_factor_user_id" not in session:
        return redirect(url_for("auth.login"))

    user = User.query.get(session["two_factor_user_id"])
    if not user:
        return redirect(url_for("auth.login"))

    if request.method == "POST":
        token = request.form.get("token")
        if user.verify_totp(token):
            login_user(user, remember=True)
            user_session = authentication_service.create_user_session(user)
            session["session_id"] = user_session.session_id
            session.pop("two_factor_user_id", None)

            # Ensure device_id cookie is set as in the normal login flow
            device_id = request.cookies.get("device_id")
            if not device_id:
                import uuid

                device_id = str(uuid.uuid4())
            resp = make_response(redirect(url_for("public.index")))
            resp.set_cookie(
                "device_id",
                device_id,
                max_age=60 * 60 * 24 * 365 * 2,
                httponly=True,
                secure=current_app.config.get("SESSION_COOKIE_SECURE", False),
            )
            return resp
        flash("Código 2FA inválido")

    return render_template("auth/verify_2fa.html", csrf_token=generate_csrf)


@auth_bp.route("/logout")
def logout():
    if current_user.is_authenticated:
        current_session_id = session.get("session_id")
        if current_session_id:
            authentication_service.terminate_session(current_session_id)
    # Clear server session and logout
    session.clear()
    logout_user()
    # Make sure the remember cookie is removed from the client
    resp = make_response(redirect(url_for("public.index")))
    remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
    resp.delete_cookie(remember_cookie_name)
    return resp


@auth_bp.route("/active_sessions")
@require_valid_session
def sesiones_activas():
    if not current_user.is_authenticated:
        return "No estás logueado", 401

    sessions = authentication_service.get_active_sessions(current_user)
    current_session_id = session.get("session_id")
    return render_template("auth/active_sessions.html", sessions=sessions, current_session_id=current_session_id)


@auth_bp.route("/terminate_session/<session_id>")
@require_valid_session
def terminate_session(session_id):
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    current_session_id = session.get("session_id")

    if session_id == current_session_id:
        flash("No puedes cerrar la sesión actual desde aquí.")
        return redirect(url_for("auth.sesiones_activas"))

    authentication_service.terminate_session(session_id)
    flash("Sesión cerrada correctamente.")
    return redirect(url_for("auth.sesiones_activas"))


@auth_bp.route("/check_session")
def check_session():
    """Endpoint para verificar si la sesión sigue activa (usado por AJAX)."""
    if not current_user.is_authenticated:
        return "", 401
    if not authentication_service.is_current_session_valid():
        logout_user()
        session.clear()
        # return a response that clears the remember cookie so the client won't be auto-logged-in
        resp = make_response(("", 401))
        remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
        resp.delete_cookie(remember_cookie_name)
        return resp
    return "", 200


@auth_bp.errorhandler(429)
def ratelimit_handler(e):
    form = LoginForm()
    return render_template("auth/login_form.html", form=form, countdown=60), 429
