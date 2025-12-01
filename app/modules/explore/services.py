import io
import os
import zipfile

from flask import current_app

from app.modules.explore.repositories import ExploreRepository
from core.services.BaseService import BaseService


class ExploreService(BaseService):
    def __init__(self):
        super().__init__(ExploreRepository())

    def filter(self, query="", sorting="newest", publication_type="any", tags=[], **kwargs):
        return self.repository.filter(query, sorting, publication_type, tags, **kwargs)

    def generate_zip_from_cart(self, dataset_ids):
        from app.modules.dataset.services import DataSetService

        dataset_service = DataSetService()

        memory_file = io.BytesIO()

        possible_roots = [
            current_app.config.get("UPLOAD_FOLDER"),
            os.path.join(os.getcwd(), "uploads"),
            os.path.join(current_app.root_path, "uploads"),
        ]

        with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
            for dataset_id in dataset_ids:
                try:
                    dataset = dataset_service.get_or_404(dataset_id)

                    user_folder = f"user_{dataset.user_id}"
                    dataset_folder = f"dataset_{dataset.id}"

                    for file in dataset.files():
                        file_name = file.name

                        for root in possible_roots:
                            if not root or not os.path.exists(root):
                                continue

                            path_struct = os.path.join(root, user_folder, dataset_folder, file_name)
                            if os.path.exists(path_struct):
                                zf.write(path_struct, f"{dataset.id}_{file_name}")
                                break

                            path_flat = os.path.join(root, file_name)
                            if os.path.exists(path_flat):
                                zf.write(path_flat, f"{dataset.id}_{file_name}")
                                break

                except Exception:
                    continue

        memory_file.seek(0)
        return memory_file
