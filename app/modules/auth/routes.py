from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_user, logout_user

from app.modules.auth import auth_bp
from app.modules.auth.forms import LoginForm, SignupForm
from app.modules.auth.models import User
from app.modules.auth.services import AuthenticationService
from app.modules.profile.services import UserProfileService

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
def login():
    if current_user.is_authenticated:
        return redirect(url_for("public.index"))

    form = LoginForm()
    if form.validate_on_submit():
        user = authentication_service.get_user_by_email(form.email.data)
        if user and authentication_service.verify_password(user, form.password.data):
            if getattr(user, "two_factor_enabled", False):
                session["two_factor_user_id"] = user.id
                logout_user()
                return redirect(url_for("auth.verify_2fa"))
            login_user(user, remember=True)
            return redirect(url_for("public.index"))

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
            session.pop("two_factor_user_id", None)
            return redirect(url_for("public.index"))
        flash("Código 2FA inválido")

    return render_template("auth/verify_2fa.html")


@auth_bp.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("public.index"))
