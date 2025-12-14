import logging
import os
import tempfile
import uuid
from datetime import datetime, timezone
from zipfile import ZipFile

import pandas as pd
from flask import abort, flash, jsonify, make_response, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user, login_required

from app import db
from app.modules.dataset import dataset_bp
from app.modules.dataset.forms import DataSetForm, FormulaDataSetForm, RawDataSetForm
from app.modules.dataset.models import DataSet, DSDownloadRecord, FormulaFile
from app.modules.dataset.services import (
    AuthorService,
    DataSetService,
    DOIMappingService,
    DSDownloadRecordService,
    DSMetaDataService,
    DSViewRecordService,
    FormulaDataSetService,
    RawDataSetService,
    UVLDataSetService,
)
from app.modules.fakenodo.services import FakenodoService

logger = logging.getLogger(__name__)

# Instanciamos los servicios genéricos (para lecturas, listados, etc.)
dataset_service = DataSetService()
author_service = AuthorService()
dsmetadata_service = DSMetaDataService()
fakenodo_service = FakenodoService()
doi_mapping_service = DOIMappingService()
ds_view_record_service = DSViewRecordService()


@dataset_bp.route("/dataset/upload", methods=["GET", "POST"])
@login_required
def create_dataset(dataset_type):
    """
    Controlador Polimórfico de Subida.
    Selecciona el servicio y el formulario adecuado según el tipo de dataset.
    """

    # 1. FACTORY: Selección de Estrategia
    if dataset_type == "uvl":
        service = UVLDataSetService()
        form = DataSetForm()
        template = "dataset/upload_dataset.html"

    elif dataset_type == "formula":
        service = FormulaDataSetService()
        form = FormulaDataSetForm()
        template = "dataset/upload_formula.html"

    elif dataset_type == "raw":
        service = RawDataSetService()
        form = RawDataSetForm()
        template = "dataset/upload_raw.html"

    else:
        return abort(404, description=f"Dataset type '{dataset_type}' not supported yet.")

    if request.method == "POST":
        if form.validate_on_submit():
            try:
                # 1. Creación del dataset local
                logger.info(f"Creating dataset of type {dataset_type}...")
                dataset = service.create_from_form(form=form, current_user=current_user)
                logger.info(f"Created dataset: {dataset}")

                # =======================================================
                # BLOQUE MODIFICADO: CONEXIÓN A FAKENODO (Mock)
                # =======================================================
                try:
                    logger.info("Connecting to Fakenodo (Mock)...")

                    # Lógica específica de movimiento de ficheros (Solo para UVL)
                    if dataset_type == "uvl":
                        service.move_feature_models(dataset)

                    # A. Crear depósito en Fakenodo
                    # Usamos el título del formulario
                    fake_meta = {"title": dataset.ds_meta_data.title}
                    deposition = fakenodo_service.create_deposition(metadata=fake_meta)
                    deposition_id = deposition.get("id")

                    # B. Simular subida de archivos
                    # Recorremos los modelos para 'fingir' que los subimos al mock
                    if dataset_type == "uvl":
                        for fm in dataset.feature_models:
                            for file in fm.files:
                                # Subimos contenido dummy o real, para el mock basta el nombre
                                fakenodo_service.upload_file(deposition_id, file.name, b"mock_content_for_speed")
                    else:
                        for file in dataset.files:
                            fakenodo_service.upload_file(deposition_id, file.name, b"mock_content_for_speed")

                    # C. Publicar en Fakenodo (Genera el DOI)
                    published_dep = fakenodo_service.publish_deposition(deposition_id)

                    # D. Guardar el DOI falso en tu base de datos local
                    if published_dep and published_dep.get("doi"):
                        dataset.ds_meta_data.deposition_id = deposition_id
                        dataset.ds_meta_data.dataset_doi = published_dep.get("doi")
                        db.session.commit()

                    flash("Dataset uploaded and synced with Fakenodo!", "success")

                except Exception as e:
                    # Si falla Fakenodo, no borramos el dataset local, solo avisamos
                    logger.error(f"Error en Fakenodo: {e}")
                    flash("Dataset saved locally, but Fakenodo sync failed.", "warning")

                return jsonify({"message": "Dataset created successfully!"}), 200

            except Exception as exc:
                logger.exception(f"Exception while create dataset: {exc}")
                return jsonify({"message": f"General error: {str(exc)}"}), 500
        else:
            return jsonify({"message": "Form validation failed"}), 400

    return render_template(template, form=form)


@dataset_bp.route("/dataset/<int:dataset_id>/duplicate", methods=["POST", "GET"])
@login_required
def duplicate_dataset(dataset_id):
    service = DataSetService()
    service.duplicate_dataset(dataset_id, current_user.id)
    return redirect(url_for("dataset.list_dataset"))


@dataset_bp.route("/dataset/list", methods=["GET", "POST"])
@login_required
def list_dataset():
    # Listar usa el servicio genérico porque solo necesitamos metadatos comunes
    return render_template(
        "dataset/list_datasets.html",
        datasets=dataset_service.get_synchronized(current_user.id),
        local_datasets=dataset_service.get_unsynchronized(current_user.id),
    )


@dataset_bp.route("/dataset/file/upload", methods=["POST"])
@login_required
def upload():
    """
    Esta ruta maneja la subida asíncrona (Dropzone) a la carpeta temporal.
    Actualmente está configurada para UVL.
    """
    file = request.files["file"]
    temp_folder = current_user.temp_folder()

    if not file or not file.filename.endswith(".uvl"):
        return jsonify({"message": "No valid file"}), 400

    # create temp folder
    if not os.path.exists(temp_folder):
        os.makedirs(temp_folder)

    file_path = os.path.join(temp_folder, file.filename)

    if os.path.exists(file_path):
        # Generate unique filename (by recursion)
        base_name, extension = os.path.splitext(file.filename)
        i = 1
        while os.path.exists(os.path.join(temp_folder, f"{base_name} ({i}){extension}")):
            i += 1
        new_filename = f"{base_name} ({i}){extension}"
        file_path = os.path.join(temp_folder, new_filename)
    else:
        new_filename = file.filename

    try:
        file.save(file_path)
    except Exception as e:
        return jsonify({"message": str(e)}), 500

    return (
        jsonify(
            {
                "message": "UVL uploaded and validated successfully",
                "filename": new_filename,
            }
        ),
        200,
    )


@dataset_bp.route("/dataset/file/delete", methods=["POST"])
def delete():
    data = request.get_json()
    filename = data.get("file")
    temp_folder = current_user.temp_folder()
    filepath = os.path.join(temp_folder, filename)

    if os.path.exists(filepath):
        os.remove(filepath)
        return jsonify({"message": "File deleted successfully"})

    return jsonify({"error": "Error: File not found"})


@dataset_bp.route("/dataset/download/<int:dataset_id>", methods=["GET"])
def download_dataset(dataset_id):
    # Usamos get_or_404 genérico. SQLalchemy nos devolverá la instancia hija correcta (UVLDataSet o RawDataSet)
    dataset = dataset_service.get_or_404(dataset_id)

    # Lógica de contador (Común)
    dataset.download_count = DataSet.download_count + 1
    db.session.commit()

    file_path = f"uploads/user_{dataset.user_id}/dataset_{dataset.id}/"

    temp_dir = tempfile.mkdtemp()
    zip_path = os.path.join(temp_dir, f"dataset_{dataset_id}.zip")

    # Generación de ZIP
    if not os.path.exists(file_path):
        os.makedirs(file_path, exist_ok=True)

    with ZipFile(zip_path, "w") as zipf:
        for subdir, dirs, files in os.walk(file_path):
            for file in files:
                full_path = os.path.join(subdir, file)
                relative_path = os.path.relpath(full_path, file_path)
                zipf.write(
                    full_path,
                    arcname=os.path.join(os.path.basename(zip_path[:-4]), relative_path),
                )

    user_cookie = request.cookies.get("download_cookie")
    if not user_cookie:
        user_cookie = str(uuid.uuid4())
        resp = make_response(
            send_from_directory(
                temp_dir,
                f"dataset_{dataset_id}.zip",
                as_attachment=True,
                mimetype="application/zip",
            )
        )
        resp.set_cookie("download_cookie", user_cookie)
    else:
        resp = send_from_directory(
            temp_dir,
            f"dataset_{dataset_id}.zip",
            as_attachment=True,
            mimetype="application/zip",
        )

    # Registro de descarga (Común)
    existing_record = DSDownloadRecord.query.filter_by(
        user_id=current_user.id if current_user.is_authenticated else None,
        dataset_id=dataset_id,
        download_cookie=user_cookie,
    ).first()

    if not existing_record:
        DSDownloadRecordService().create(
            user_id=current_user.id if current_user.is_authenticated else None,
            dataset_id=dataset_id,
            download_date=datetime.now(timezone.utc),
            download_cookie=user_cookie,
        )

    return resp


@dataset_bp.route("/doi/<path:doi>/", methods=["GET"])
def subdomain_index(doi):
    new_doi = doi_mapping_service.get_new_doi(doi)
    if new_doi:
        return redirect(url_for("dataset.subdomain_index", doi=new_doi), code=302)

    ds_meta_data = dsmetadata_service.filter_by_doi(doi)

    if not ds_meta_data:
        abort(404)

    dataset = ds_meta_data.data_set

    user_cookie = ds_view_record_service.create_cookie(dataset=dataset)
    resp = make_response(render_template("dataset/view_dataset.html", dataset=dataset))
    resp.set_cookie("view_cookie", user_cookie)

    return resp


@dataset_bp.route("/dataset/unsynchronized/<int:dataset_id>/", methods=["GET"])
@login_required
def get_unsynchronized_dataset(dataset_id):
    dataset = dataset_service.get_unsynchronized_dataset(current_user.id, dataset_id)
    if not dataset:
        abort(404)
    return render_template("dataset/view_dataset.html", dataset=dataset)


@dataset_bp.route("/dataset/view/<int:dataset_id>", methods=["GET"])
def view_dataset(dataset_id):
    dataset = dataset_service.get_or_404(dataset_id)
    if current_user.is_authenticated and dataset.user_id != current_user.id:
        abort(403)
    return render_template("dataset/view_dataset.html", dataset=dataset)


@dataset_bp.route("/dataset/formula/file_preview/<int:file_id>", methods=["GET"])
def get_formula_file_preview(file_id):
    file = FormulaFile.query.get_or_404(file_id)

    file_path = file.get_path()

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found on disk"}), 404

    try:
        df = pd.read_csv(file_path, nrows=15)

        html_content = df.to_html(classes="table table-striped table-sm table-hover", index=False, border=0)
        return jsonify({"content": html_content})

    except Exception as e:
        return jsonify({"error": f"Error reading CSV: {str(e)}"}), 500
