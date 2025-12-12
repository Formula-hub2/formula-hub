from flask import current_app, flash, jsonify, redirect, render_template, request, send_from_directory, url_for
from flask_login import current_user

from app import db
from app.modules.dataset.models import DSMetaData
from app.modules.dataset.services import DataSetService
from app.modules.fakenodo import fakenodo_bp
from app.modules.fakenodo.services import service as fakenodo_service


@fakenodo_bp.route("/", methods=["GET"], endpoint="index")
def index():
    if request.accept_mimetypes.accept_html:
        deposits = fakenodo_service.list_depositions()
        return render_template("fakenodo/index.html", deposits=deposits)
    return jsonify({"status": "ok", "message": "Fakenodo mock alive"})


@fakenodo_bp.route("/deposit/depositions", methods=["POST"], endpoint="create_deposition")
def create_deposition():
    payload = request.get_json(silent=True) or {}
    metadata = payload.get("metadata") if isinstance(payload, dict) else {}
    created = fakenodo_service.create_deposition(metadata=metadata)
    return jsonify(created), 201


@fakenodo_bp.route("/deposit/depositions", methods=["GET"], endpoint="list_depositions")
def list_depositions():
    return jsonify({"depositions": fakenodo_service.list_depositions()}), 200


@fakenodo_bp.route("/deposit/depositions/<int:deposition_id>", methods=["GET"], endpoint="get_deposition")
def get_deposition(deposition_id: int):
    rec = fakenodo_service.get_deposition(deposition_id)

    # 1. Si no existe el depósito
    if not rec:
        return jsonify({"message": "Depósito no encontrado"}), 404

    # 2. Si es el navegador (pide HTML), mostramos la plantilla bonita
    if request.accept_mimetypes.accept_html:
        return render_template("fakenodo/deposition.html", deposit=rec)

    # 3. Si es la API (pide JSON), devolvemos los datos crudos
    return jsonify(rec), 200


@fakenodo_bp.route("/deposit/depositions/<int:deposition_id>", methods=["DELETE"], endpoint="delete_deposition")
def delete_deposition(deposition_id: int):
    ok = fakenodo_service.delete_deposition(deposition_id)
    return (
        (jsonify({"status": "removed", "id": deposition_id}), 200)
        if ok
        else (jsonify({"message": "Depósito no encontrado"}), 404)
    )


@fakenodo_bp.route("/deposit/depositions/<int:deposition_id>/files", methods=["POST"], endpoint="upload_file")
def upload_file(deposition_id: int):
    uploaded = request.files.get("file")
    name = request.form.get("name") or (uploaded.filename if uploaded else None)
    if not name:
        return jsonify({"message": "Nombre de fichero no proporcionado"}), 400
    content = uploaded.read() if uploaded else None
    file_record = fakenodo_service.upload_file(deposition_id, name, content)
    return (jsonify(file_record), 201) if file_record else (jsonify({"message": "Depósito no encontrado"}), 404)


@fakenodo_bp.route(
    "/deposit/depositions/<int:deposition_id>/actions/publish", methods=["POST"], endpoint="publish_deposition"
)
def publish_deposition(deposition_id: int):
    result = fakenodo_service.publish_deposition(deposition_id)
    if not result:
        return jsonify({"message": "Depósito no encontrado"}), 404

    try:
        ds_meta = DSMetaData.query.filter_by(deposition_id=deposition_id).first()
        if ds_meta:
            ds_meta.dataset_doi = result.get("doi")
            db.session.commit()
    except Exception:
        pass

    if request.accept_mimetypes.accept_html:
        flash(f"Depósito {deposition_id} publicado (doi={result.get('doi')})", "success")
        return redirect(url_for("fakenodo.index"))

    return jsonify(result), 202


@fakenodo_bp.route(
    "/deposit/depositions/<int:deposition_id>/metadata", methods=["PATCH"], endpoint="update_deposition_metadata"
)
def update_deposition_metadata(deposition_id: int):
    payload = request.get_json(silent=True) or {}
    metadata = (
        payload.get("metadata")
        if isinstance(payload.get("metadata"), dict)
        else {
            k: v
            for k, v in payload.items()
            if k in ["title", "description", "tags", "publication_type", "publication_doi"]
        }
    )
    if isinstance(metadata.get("tags"), list):
        metadata["tags"] = ",".join(t.strip() for t in metadata["tags"] if t and isinstance(t, str))

    updated = fakenodo_service.update_metadata(deposition_id, metadata)
    if not updated:
        return jsonify({"message": "Depósito no encontrado"}), 404

    try:
        dsmeta = DSMetaData.query.filter_by(deposition_id=deposition_id).first()
        if dsmeta:
            for field in ["title", "description", "tags"]:
                if field in metadata and getattr(dsmeta, field) != metadata[field]:
                    setattr(dsmeta, field, metadata[field])
            db.session.commit()
    except Exception:
        pass

    # Obtener versiones explícitamente del servicio
    versions = fakenodo_service.list_versions(deposition_id)

    return (
        jsonify(
            {
                "id": deposition_id,
                "metadata": updated.get("metadata"),
                "dirty": updated.get("dirty_files"),  # Corregido para usar nombre interno del servicio
                "versions": versions,
            }
        ),
        200,
    )


@fakenodo_bp.route("/deposit/depositions/<int:deposition_id>/versions", methods=["GET"], endpoint="list_versions")
def list_versions(deposition_id: int):
    dep = fakenodo_service.get_deposition(deposition_id)
    if not dep:
        return jsonify({"message": "Depósito no encontrado", "versions": []}), 404
    return jsonify({"versions": fakenodo_service.list_versions(deposition_id) or []}), 200


@fakenodo_bp.route("/test", methods=["GET"], endpoint="test_endpoint")
def test_endpoint():
    return fakenodo_service.test_full_connection()


# --- Dataset Integration Proxies ---


@fakenodo_bp.route("/dataset/<int:dataset_id>/sync", methods=["GET", "POST"], endpoint="dataset_sync_proxy")
def dataset_sync_proxy(dataset_id=None):
    if request.method == "GET":
        return redirect(url_for("dataset.get_unsynchronized_dataset", dataset_id=dataset_id))
    view_fn = current_app.view_functions.get("dataset.sync_dataset")
    if view_fn:
        return view_fn(dataset_id)
    return jsonify({"message": "Sync handler not available"}), 500


@fakenodo_bp.route("/dataset/<int:dataset_id>/create", methods=["POST"], endpoint="create_dataset_deposition")
def create_dataset_deposition(dataset_id: int):
    ds_service = DataSetService()
    ds = ds_service.repository.get_by_id(dataset_id)
    meta = getattr(ds, "ds_meta_data", None) if ds else None
    if not ds or not meta or not (current_user and current_user.is_authenticated and ds.user_id == current_user.id):
        return redirect(url_for("dataset.list_dataset"))
    if getattr(meta, "dataset_doi", None) or getattr(meta, "deposition_id", None):
        return redirect(url_for("dataset.list_dataset"))
    resp = fakenodo_service.create_deposition(metadata={"title": meta.title})
    deposition_id = resp.get("id") if resp else None
    if deposition_id:
        ds_service.update_dsmetadata(ds.ds_meta_data_id, deposition_id=deposition_id)
    return redirect(url_for("dataset.get_unsynchronized_dataset", dataset_id=dataset_id))


@fakenodo_bp.route("/dataset/<int:dataset_id>/publish", methods=["POST"], endpoint="publish_dataset_deposition")
def publish_dataset_deposition(dataset_id: int):
    ds_service = DataSetService()
    ds = ds_service.repository.get_by_id(dataset_id)
    meta = getattr(ds, "ds_meta_data", None) if ds else None
    if not ds or not meta or not (current_user and current_user.is_authenticated and ds.user_id == current_user.id):
        return redirect(url_for("dataset.list_dataset"))
    if getattr(meta, "dataset_doi", None):
        return redirect(url_for("dataset.list_dataset"))
    deposition_id = getattr(meta, "deposition_id", None)
    if not deposition_id:
        return redirect(url_for("dataset.get_unsynchronized_dataset", dataset_id=dataset_id))
    for fm in getattr(ds, "feature_models", []) + getattr(ds, "file_models", []):
        try:
            fname = getattr(fm, "filename", None) or getattr(fm, "name", f'fm_{getattr(fm, "id", "?")}.bin')
            fakenodo_service.upload_file(deposition_id, fname, None)
        except Exception:
            pass
    version = fakenodo_service.publish_deposition(deposition_id)
    if version:
        doi = fakenodo_service.get_doi(deposition_id)
        ds_service.update_dsmetadata(ds.ds_meta_data_id, dataset_doi=doi)
    return redirect(url_for("dataset.list_dataset"))


@fakenodo_bp.route(
    "/dataset/<int:dataset_id>/publish_or_create", methods=["POST"], endpoint="publish_or_create_dataset_deposition"
)
def publish_or_create_dataset_deposition(dataset_id: int):
    ds_service = DataSetService()
    ds = ds_service.repository.get_by_id(dataset_id)
    meta = getattr(ds, "ds_meta_data", None) if ds else None
    if not ds or not meta or not (current_user and current_user.is_authenticated and ds.user_id == current_user.id):
        return redirect(url_for("dataset.list_dataset"))

    deposition_id = getattr(meta, "deposition_id", None)
    if not deposition_id:
        resp = fakenodo_service.create_deposition(metadata={"title": meta.title})
        deposition_id = resp.get("id") if resp else None
        if deposition_id:
            ds_service.update_dsmetadata(ds.ds_meta_data_id, deposition_id=deposition_id)

    if not deposition_id:
        return redirect(url_for("dataset.get_unsynchronized_dataset", dataset_id=dataset_id))

    for fm in getattr(ds, "feature_models", []) + getattr(ds, "file_models", []):
        try:
            fname = getattr(fm, "filename", None) or getattr(fm, "name", f'fm_{getattr(fm, "id", "?")}.bin')
            fakenodo_service.upload_file(deposition_id, fname, None)
        except Exception:
            pass
    version = fakenodo_service.publish_deposition(deposition_id)
    if version:
        doi = fakenodo_service.get_doi(deposition_id)
        ds_service.update_dsmetadata(ds.ds_meta_data_id, dataset_doi=doi)

    return redirect(url_for("dataset.list_dataset"))


@fakenodo_bp.route("/scripts.js")
def scripts():
    return send_from_directory(fakenodo_bp.static_folder, "scripts.js")


@fakenodo_bp.route("/visualize/<int:dataset_id>", methods=["GET"])
def visualize_local_dataset(dataset_id):
    """
    Crea una visualización falsa 'al vuelo' para datasets antiguos
    que no están realmente en Fakenodo.
    """
    # 1. Obtenemos el dataset real de la base de datos
    ds_service = DataSetService()
    dataset = ds_service.repository.get_by_id(dataset_id)

    if not dataset:
        return render_template("404.html"), 404

    # 2. Construimos un objeto 'falso' que tenga la estructura que espera la plantilla
    # La plantilla espera: deposit.metadata.title, deposit.files, deposit.doi, etc.

    # Recopilamos archivos
    files_list = []
    for fm in dataset.feature_models:
        for f in fm.files:
            files_list.append({"filename": f.name, "checksum": f.checksum, "filesize": f.size})

    fake_deposit = {
        "id": dataset.id,
        "metadata": {
            "title": dataset.ds_meta_data.title,
            "description": dataset.ds_meta_data.description,
        },
        "title": dataset.ds_meta_data.title,  # Por si acaso
        "doi": dataset.ds_meta_data.dataset_doi or "Internal-ID",
        "created": dataset.created_at.strftime("%Y-%m-%d") if dataset.created_at else "Unknown",
        "modified": "Simulated View",
        "version_count": 1,
        "files": files_list,
    }

    # 3. Renderizamos la MISMA plantilla que usan los de Fakenodo
    return render_template("fakenodo/deposition.html", deposit=fake_deposit)
