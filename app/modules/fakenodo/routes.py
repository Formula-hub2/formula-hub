from flask import flash, jsonify, redirect, render_template, request, send_from_directory, url_for

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
    if not rec:
        return jsonify({"message": "Depósito no encontrado"}), 404

    if request.accept_mimetypes.accept_html:
        return render_template("fakenodo/deposition.html", deposit=rec)

    return jsonify(rec), 200


@fakenodo_bp.route("/deposit/depositions/<int:deposition_id>", methods=["DELETE"], endpoint="delete_deposition")
def delete_deposition(deposition_id: int):
    ok = fakenodo_service.delete_deposition(deposition_id)
    return (
        (jsonify({"status": "removed", "id": deposition_id}), 200) if ok else (jsonify({"message": "Not found"}), 404)
    )


@fakenodo_bp.route("/deposit/depositions/<int:deposition_id>/files", methods=["POST"], endpoint="upload_file")
def upload_file(deposition_id: int):
    uploaded = request.files.get("file")
    name = request.form.get("name") or (uploaded.filename if uploaded else None)
    if not name:
        return jsonify({"message": "No filename"}), 400
    content = uploaded.read() if uploaded else None
    file_record = fakenodo_service.upload_file(deposition_id, name, content)
    return (jsonify(file_record), 201) if file_record else (jsonify({"message": "Not found"}), 404)


@fakenodo_bp.route(
    "/deposit/depositions/<int:deposition_id>/actions/publish", methods=["POST"], endpoint="publish_deposition"
)
def publish_deposition(deposition_id: int):
    result = fakenodo_service.publish_deposition(deposition_id)
    if not result:
        return jsonify({"message": "Not found"}), 404

    try:
        ds_meta = DSMetaData.query.filter_by(deposition_id=deposition_id).first()
        if ds_meta:
            ds_meta.dataset_doi = result.get("doi")
            db.session.commit()
    except Exception:
        pass

    if request.accept_mimetypes.accept_html:  # Redirección para el dashboard
        flash(f"Depósito {deposition_id} publicado.", "success")
        return redirect(url_for("fakenodo.index"))

    return jsonify(result), 202


@fakenodo_bp.route(
    "/deposit/depositions/<int:deposition_id>/metadata", methods=["PATCH"], endpoint="update_deposition_metadata"
)
def update_deposition_metadata(deposition_id: int):

    payload = request.get_json(silent=True) or {}
    metadata = payload.get("metadata", {})
    updated = fakenodo_service.update_metadata(deposition_id, metadata)
    if not updated:
        return jsonify({"message": "Not found"}), 404
    return jsonify(updated), 200


@fakenodo_bp.route("/test", methods=["GET"], endpoint="test_endpoint")
def test_endpoint():
    return fakenodo_service.test_full_connection()


@fakenodo_bp.route("/scripts.js")
def scripts():
    return send_from_directory(fakenodo_bp.static_folder, "scripts.js")


@fakenodo_bp.route("/reset", methods=["POST"], endpoint="reset")
def reset():
    fakenodo_service.reset()
    return jsonify({"message": "Fakenodo reset successful"}), 200


@fakenodo_bp.route("/visualize/<int:dataset_id>", methods=["GET"])
def visualize_local_dataset(dataset_id):
    """
    Simula una vista de Zenodo para datasets que están solo en UVLHub (SQL).
    """
    ds_service = DataSetService()
    dataset = ds_service.repository.get_by_id(dataset_id)

    if not dataset:
        return render_template("404.html"), 404

    files_list = []

    try:
        for f in dataset.files():
            checksum = getattr(f, "checksum", "N/A")

            files_list.append({"filename": f.name, "checksum": checksum, "filesize": f.size})

    except Exception as e:
        print(f"Error procesando archivos para visualización: {e}")
        pass

    fake_deposit = {
        "id": dataset.id,
        "metadata": {
            "title": dataset.ds_meta_data.title,
            "description": dataset.ds_meta_data.description,
        },
        "title": dataset.ds_meta_data.title,
        "doi": dataset.ds_meta_data.dataset_doi or "Internal-ID",
        "created": dataset.created_at.strftime("%Y-%m-%d") if dataset.created_at else "Unknown",
        "modified": "Simulated View",
        "version_count": 1,
        "files": files_list,
        "submitted": True,
    }

    return render_template("fakenodo/deposition.html", deposit=fake_deposit)
