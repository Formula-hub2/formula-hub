from flask import Blueprint

fakenodo_bp = Blueprint(
    "fakenodo",
    __name__,
    url_prefix="/fakenodo",
    template_folder="templates",
    static_folder="assets",
    static_url_path="/fakenodo/static",
)

from . import routes