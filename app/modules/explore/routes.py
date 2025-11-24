import logging

from flask import jsonify, render_template, request, send_file
from flask_login import current_user, login_required

from app.modules.dataset.services import DataSetService
from app.modules.explore import explore_bp
from app.modules.explore.forms import ExploreForm
from app.modules.explore.services import ExploreService

logger = logging.getLogger(__name__)

dataset_service = DataSetService()


@explore_bp.route("/explore", methods=["GET", "POST"])
def index():
    if request.method == "GET":
        query = request.args.get("query", "")
        form = ExploreForm()
        return render_template("explore/index.html", form=form, query=query)

    if request.method == "POST":
        criteria = request.get_json()
        explore_service = ExploreService()

        # Incluir datasets no sincronizados
        datasets = explore_service.filter(
            query=criteria.get("query", ""),
            sorting=criteria.get("sorting", "newest"),
            publication_type=criteria.get("publication_type", "any"),
            tags=criteria.get("tags", []),
            include_unsynchronized=True,
        )
        return jsonify([dataset.to_dict() for dataset in datasets])


@explore_bp.route("/explore/create-dataset-from-cart", methods=["POST"])
@login_required
def create_dataset_from_cart():
    try:
        title = request.form.get("title")
        description = request.form.get("description")
        publication_type = request.form.get("publication_type")
        tags = request.form.get("tags")
        selected_datasets = request.form.get("selected_datasets", "")

        # Convertir string de IDs a lista
        source_dataset_ids = [
            int(id.strip()) for id in selected_datasets.split(",") if id.strip()
        ]

        created_dataset = dataset_service.create_combined_dataset(
            current_user=current_user,
            title=title,
            description=description,
            publication_type=publication_type,  # ← Pasar el publication_type
            tags=tags,
            source_dataset_ids=source_dataset_ids,
        )

        return jsonify(
            {
                "success": True,
                "message": "Dataset created successfully",
                "dataset_id": created_dataset.id,
            }
        )

    except Exception as e:
        return jsonify(
            {"success": False, "message": f"Error creating dataset: {str(e)}"}
        ), 500


@explore_bp.route("/explore/download_cart", methods=["POST"])
def download_cart():
    try:
        data = request.get_json()
        dataset_ids = data.get("dataset_ids", [])
        filename = data.get("filename", "my_uvlhub_models")

        if not filename.endswith(".zip"):
            filename += ".zip"

        if not dataset_ids:
            return jsonify({"success": False, "message": "No datasets selected"}), 400

        explore_service = ExploreService()
        zip_buffer = explore_service.generate_zip_from_cart(dataset_ids)

        return send_file(
            zip_buffer,
            mimetype="application/zip",
            as_attachment=True,
            download_name=filename,
        )
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500
