import os
import traceback
import uuid
from datetime import datetime, timezone

from flask import current_app, jsonify, make_response, request, send_from_directory, url_for
from flask_login import current_user

from app import db
from app.modules.hubfile import hubfile_bp
from app.modules.hubfile.models import HubfileDownloadRecord, HubfileViewRecord
from app.modules.hubfile.services import HubfileDownloadRecordService, HubfileService


@hubfile_bp.route("/file/download/<int:file_id>", methods=["GET"])
def download_file(file_id):
    file = HubfileService().get_or_404(file_id)
    filename = file.name

    directory_path = (
        f"uploads/user_{file.feature_model.uvl_dataset.user_id}/dataset_{file.feature_model.uvl_dataset_id}/"
    )
    parent_directory_path = os.path.dirname(current_app.root_path)
    file_path = os.path.join(parent_directory_path, directory_path)

    # Get the cookie from the request or generate a new one if it does not exist
    user_cookie = request.cookies.get("file_download_cookie")
    if not user_cookie:
        user_cookie = str(uuid.uuid4())

    # Check if the download record already exists for this cookie
    existing_record = HubfileDownloadRecord.query.filter_by(
        user_id=current_user.id if current_user.is_authenticated else None, file_id=file_id, download_cookie=user_cookie
    ).first()

    if not existing_record:
        # Record the download in your database
        HubfileDownloadRecordService().create(
            user_id=current_user.id if current_user.is_authenticated else None,
            file_id=file_id,
            download_date=datetime.now(timezone.utc),
            download_cookie=user_cookie,
        )

    # Save the cookie to the user's browser
    resp = make_response(send_from_directory(directory=file_path, path=filename, as_attachment=True))
    resp.set_cookie("file_download_cookie", user_cookie)

    return resp


@hubfile_bp.route("/file/view/<int:file_id>", methods=["GET"])
def view_file(file_id):
    file = HubfileService().get_or_404(file_id)
    filename = file.name

    directory_path = (
        f"uploads/user_{file.feature_model.uvl_dataset.user_id}/dataset_{file.feature_model.uvl_dataset_id}/"
    )
    parent_directory_path = os.path.dirname(current_app.root_path)

    # Ruta completa a la CARPETA (necesaria para send_from_directory)
    full_dir_path = os.path.join(parent_directory_path, directory_path)
    # Ruta completa al ARCHIVO (necesaria para open)
    file_path = os.path.join(full_dir_path, filename)

    try:
        if os.path.exists(file_path):
            # En lugar de enviar el binario, enviamos un JSON con HTML que apunta a la descarga
            ext = os.path.splitext(filename)[1].lower()
            download_url = url_for("hubfile.download_file", file_id=file_id)

            content = ""

            if ext in [".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp"]:
                # Si es imagen, devolvemos una etiqueta IMG
                content = f'<div style="text-align: center;"><img src="{download_url}" style="max-width: 100%; max-height: 600px; border-radius: 4px;" alt="Image preview"></div>'

            elif ext == ".pdf":
                # Si es PDF, devolvemos un IFRAME
                content = f'<iframe src="{download_url}" style="width: 100%; height: 600px;" frameborder="0"></iframe>'

            else:
                # --- SI ES TEXTO (.uvl, .txt, etc) ---
                # Intentamos leer el contenido real
                try:
                    with open(file_path, "r") as f:
                        # Leemos y escapamos caracteres especiales si fuera necesario,
                        # pero por ahora confiamos en el lector de texto
                        content = f.read()
                except UnicodeDecodeError:
                    return jsonify({"success": False, "error": "Binary file cannot be previewed"}), 400

            user_cookie = request.cookies.get("view_cookie")
            if not user_cookie:
                user_cookie = str(uuid.uuid4())

            # Check if the view record already exists for this cookie
            existing_record = HubfileViewRecord.query.filter_by(
                user_id=current_user.id if current_user.is_authenticated else None,
                file_id=file_id,
                view_cookie=user_cookie,
            ).first()

            if not existing_record:
                # Register file view
                new_view_record = HubfileViewRecord(
                    user_id=current_user.id if current_user.is_authenticated else None,
                    file_id=file_id,
                    view_date=datetime.now(),
                    view_cookie=user_cookie,
                )
                db.session.add(new_view_record)
                db.session.commit()

            # Prepare response
            response = jsonify({"success": True, "content": content})
            if not request.cookies.get("view_cookie"):
                response = make_response(response)
                response.set_cookie("view_cookie", user_cookie, max_age=60 * 60 * 24 * 365 * 2)

            return response
        else:
            return jsonify({"success": False, "error": "File not found"}), 404
    except Exception as e:
        print(f"ERROR CRÍTICO EN VIEW_FILE: {str(e)}")
        traceback.print_exc()
        return jsonify({"success": False, "error": str(e)}), 500
