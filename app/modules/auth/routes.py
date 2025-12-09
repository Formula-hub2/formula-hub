import os

from flask import flash, redirect, render_template, request, session, url_for
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_login import current_user, login_user, logout_user

# Necesario para el locust test de 2FA
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

        # Log user
        login_user(user, remember=True)
        return redirect(url_for("public.index"))

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
            ################################################
            device_id = request.cookies.get("device_id")
            if not device_id:
                import uuid

                device_id = str(uuid.uuid4())
            ###############################################
            login_user(user, remember=True)
            authentication_service.repository.reset_failed_attempts(user)
            # --- Crear registro de sesión ---
            user_session = authentication_service.create_user_session(user)
            session["session_id"] = user_session.session_id
            # return redirect(url_for("public.index"))
            from flask import make_response

            resp = make_response(redirect(url_for("public.index")))
            resp.set_cookie("device_id", device_id, max_age=60 * 60 * 24 * 365 * 2, httponly=True, secure=True)
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
            # --- Crear registro de sesión ---
            user_session = authentication_service.create_user_session(user)
            session["session_id"] = user_session.session_id
            session.pop("two_factor_user_id", None)
            return redirect(url_for("public.index"))
        flash("Código 2FA inválido")

    return render_template("auth/verify_2fa.html", csrf_token=generate_csrf)


@auth_bp.route("/logout")
def logout():
    # --- Crear registro de sesión ---
    if current_user.is_authenticated:
        current_session_id = session.get("session_id")
        if current_session_id:
            authentication_service.terminate_session(current_session_id)

    session.pop("session_id", None)
    logout_user()
    return redirect(url_for("public.index"))


# --- Rutas de sesiones activas ---
@auth_bp.route("/active_sessions")
def sesiones_activas():
    if not current_user.is_authenticated:
        return "No estás logueado", 401

    sessions = authentication_service.get_active_sessions(current_user)
    current_session_id = session.get("session_id")  # ID de la sesión actual
    return render_template("auth/active_sessions.html", sessions=sessions, current_session_id=current_session_id)


# --- Método para active sessions ---
@auth_bp.route("/terminate_session/<session_id>")
def terminate_session(session_id):
    if not current_user.is_authenticated:
        return redirect(url_for("auth.login"))

    current_session_id = session.get("session_id")

    # Evitar cerrar la sesión actual desde el enlace (opcional)
    if session_id == current_session_id:
        flash("No puedes cerrar la sesión actual desde aquí.")
        return redirect(url_for("auth.sesiones_activas"))

    authentication_service.terminate_session(session_id)
    flash("Sesión cerrada correctamente.")
    return redirect(url_for("auth.sesiones_activas"))


@auth_bp.errorhandler(429)
def ratelimit_handler(e):
    form = LoginForm()

    return render_template("auth/login_form.html", form=form, countdown=60), 429
