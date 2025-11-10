import base64
from io import BytesIO

import pyotp
import qrcode
from flask import flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required

from app import db
from app.modules.auth.services import AuthenticationService
from app.modules.dataset.models import DataSet
from app.modules.profile import profile_bp
from app.modules.profile.forms import UserProfileForm
from app.modules.profile.services import UserProfileService


@profile_bp.route("/profile/edit", methods=["GET", "POST"])
@login_required
def edit_profile():
    auth_service = AuthenticationService()
    profile = auth_service.get_authenticated_user_profile
    if not profile:
        return redirect(url_for("public.index"))

    form = UserProfileForm()
    if request.method == "POST":
        service = UserProfileService()
        result, errors = service.update_profile(profile.id, form)
        return service.handle_service_response(
            result, errors, "profile.edit_profile", "Profile updated successfully", "profile/edit.html", form
        )

    return render_template("profile/edit.html", form=form)


@profile_bp.route("/profile/summary")
@login_required
def my_profile():
    page = request.args.get("page", 1, type=int)
    per_page = 5

    user_datasets_pagination = (
        db.session.query(DataSet)
        .filter(DataSet.user_id == current_user.id)
        .order_by(DataSet.created_at.desc())
        .paginate(page=page, per_page=per_page, error_out=False)
    )

    total_datasets_count = db.session.query(DataSet).filter(DataSet.user_id == current_user.id).count()

    print(user_datasets_pagination.items)

    return render_template(
        "profile/summary.html",
        user_profile=current_user.profile,
        user=current_user,
        datasets=user_datasets_pagination.items,
        pagination=user_datasets_pagination,
        total_datasets=total_datasets_count,
    )


@profile_bp.route("/profile/enable_2fa", methods=["GET", "POST"])
@login_required
def enable_2fa():
    user = current_user

    # Si ya tiene 2FA activado, no permitir reactivar
    if user.two_factor_enabled:
        flash("2FA ya está activado")
        return redirect(url_for("profile.edit_profile"))

    # Solo generar secret si no lo tiene todavía
    if not user.two_factor_secret:
        user.two_factor_secret = pyotp.random_base32()
        db.session.commit()

    # Crear la URI y QR en base al secret existente
    uri = pyotp.TOTP(user.two_factor_secret).provisioning_uri(name=user.email, issuer_name="FormulaHub")
    img = qrcode.make(uri)
    buf = BytesIO()
    img.save(buf, format="PNG")
    qr_b64 = base64.b64encode(buf.getvalue()).decode()

    # Verificar el token enviado por el usuario
    if request.method == "POST":
        token = request.form.get("token")
        if pyotp.TOTP(user.two_factor_secret).verify(token):
            user.two_factor_enabled = True
            db.session.commit()
            flash("2FA activado correctamente", "success")
            return redirect(url_for("profile.edit_profile"))
        else:
            flash("Código inválido, inténtalo de nuevo", "danger")

    return render_template("profile/enable_2fa.html", qr_b64=qr_b64, secret=user.two_factor_secret)
