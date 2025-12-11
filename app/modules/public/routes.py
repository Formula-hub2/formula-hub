import logging

from flask import current_app, flash, make_response, redirect, render_template, session, url_for
from flask_login import current_user, logout_user

from app.modules.auth.services import AuthenticationService
from app.modules.dataset.services import DataSetService
from app.modules.featuremodel.services import FeatureModelService
from app.modules.public import public_bp

logger = logging.getLogger(__name__)


@public_bp.route("/")
def index():
    logger.info("Access index")

    # If the user is authenticated, ensure the session is still valid. If not,
    # force server-side logout and clear the remember cookie so the client won't
    # be auto-logged-in again.
    try:
        if current_user.is_authenticated:
            auth_service = AuthenticationService()
            if not auth_service.is_current_session_valid():
                logout_user()
                session.clear()
                flash("Tu sesión ha sido cerrada desde otro dispositivo.", "warning")
                # Redirect to the login page (exempt from session validation)
                # to avoid redirect loops when the public index is checked.
                resp = make_response(redirect(url_for("auth.login")))
                remember_cookie_name = current_app.config.get("REMEMBER_COOKIE_NAME", "remember_token")
                resp.delete_cookie(
                    remember_cookie_name,
                    path=current_app.config.get("REMEMBER_COOKIE_PATH", "/"),
                    domain=current_app.config.get("REMEMBER_COOKIE_DOMAIN"),
                )
                return resp
    except Exception:
        # If something goes wrong during validation, log out defensively.
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

    dataset_service = DataSetService()
    feature_model_service = FeatureModelService()

    # Statistics: total datasets and feature models
    datasets_counter = dataset_service.count_synchronized_datasets()
    feature_models_counter = feature_model_service.count_feature_models()

    # Statistics: total downloads
    total_dataset_downloads = dataset_service.total_dataset_downloads()
    total_feature_model_downloads = feature_model_service.total_feature_model_downloads()

    # Statistics: total views
    total_dataset_views = dataset_service.total_dataset_views()
    total_feature_model_views = feature_model_service.total_feature_model_views()

    return render_template(
        "public/index.html",
        datasets=dataset_service.latest_synchronized(),
        datasets_counter=datasets_counter,
        feature_models_counter=feature_models_counter,
        total_dataset_downloads=total_dataset_downloads,
        total_feature_model_downloads=total_feature_model_downloads,
        total_dataset_views=total_dataset_views,
        total_feature_model_views=total_feature_model_views,
    )
