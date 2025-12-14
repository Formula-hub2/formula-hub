import os
import shutil
from datetime import datetime, timezone

from dotenv import load_dotenv
from flask import current_app

from app.modules.auth.models import User
from app.modules.dataset.models import (
    Author,
    DSMetaData,
    DSMetrics,
    FormulaDataSet,
    FormulaFile,
    PublicationType,
    UVLDataSet,
)
from app.modules.featuremodel.models import FeatureModel, FMMetaData
from app.modules.hubfile.models import Hubfile
from core.seeders.BaseSeeder import BaseSeeder


class DataSetSeeder(BaseSeeder):

    priority = 2  # Lower priority

    def run(self):
        # Retrieve users
        user1 = User.query.filter_by(email="user1@example.com").first()
        user2 = User.query.filter_by(email="user2@example.com").first()

        if not user1 or not user2:
            raise Exception("Users not found. Please seed users first.")

        # Configurar directorios base
        load_dotenv()
        working_dir = os.getenv("WORKING_DIR", "")
        if not working_dir:
            working_dir = os.path.abspath(os.getcwd())

        # ==============================================================================
        # PARTE 1: UVL DATASETS
        # ==============================================================================

        # Create DSMetrics instance
        ds_metrics = DSMetrics(number_of_models="5", number_of_features="50")
        seeded_ds_metrics = self.seed([ds_metrics])[0]

        # Create DSMetaData instances
        ds_meta_data_list = [
            DSMetaData(
                deposition_id=1 + i,
                title=f"Sample dataset {i+1}",
                description=f"Description for dataset {i+1}",
                publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
                publication_doi=f"10.1234/dataset{i+1}",
                dataset_doi=f"10.1234/dataset{i+1}",
                tags="tag1, tag2",
                ds_metrics_id=seeded_ds_metrics.id,
            )
            for i in range(4)
        ]
        seeded_ds_meta_data = self.seed(ds_meta_data_list)

        # Create Author instances and associate with DSMetaData
        authors = [
            Author(
                name=f"Author {i+1}",
                affiliation=f"Affiliation {i+1}",
                orcid=f"0000-0000-0000-000{i}",
                ds_meta_data_id=seeded_ds_meta_data[i % 4].id,
            )
            for i in range(4)
        ]
        self.seed(authors)

        # Create UVLDataSet instances
        datasets = [
            UVLDataSet(
                user_id=user1.id if i % 2 == 0 else user2.id,
                ds_meta_data_id=seeded_ds_meta_data[i].id,
                created_at=datetime.now(timezone.utc),
                dataset_type="uvl_dataset",
            )
            for i in range(4)
        ]
        seeded_datasets = self.seed(datasets)

        # Assume there are 12 UVL files, create corresponding FMMetaData and FeatureModel
        fm_meta_data_list = [
            FMMetaData(
                uvl_filename=f"file{i+1}.uvl",
                title=f"Feature Model {i+1}",
                description=f"Description for feature model {i+1}",
                publication_type=PublicationType.SOFTWARE_DOCUMENTATION,
                publication_doi=f"10.1234/fm{i+1}",
                tags="tag1, tag2",
                uvl_version="1.0",
            )
            for i in range(12)
        ]
        seeded_fm_meta_data = self.seed(fm_meta_data_list)

        # Create Author instances and associate with FMMetaData
        fm_authors = [
            Author(
                name=f"Author {i+5}",
                affiliation=f"Affiliation {i+5}",
                orcid=f"0000-0000-0000-000{i+5}",
                fm_meta_data_id=seeded_fm_meta_data[i].id,
            )
            for i in range(12)
        ]
        self.seed(fm_authors)

        feature_models = [
            FeatureModel(uvl_dataset_id=seeded_datasets[i // 3].id, fm_meta_data_id=seeded_fm_meta_data[i].id)
            for i in range(12)
        ]
        seeded_feature_models = self.seed(feature_models)

        # Create files, associate them with FeatureModels and copy files
        uvl_src_folder = os.path.join(working_dir, "app", "modules", "dataset", "uvl_examples")

        for i in range(12):
            file_name = f"file{i+1}.uvl"
            if not os.path.exists(os.path.join(uvl_src_folder, file_name)):
                continue

            feature_model = seeded_feature_models[i]
            dataset = next(ds for ds in seeded_datasets if ds.id == feature_model.uvl_dataset_id)
            user_id = dataset.user_id

            dest_folder = os.path.join(working_dir, "uploads", f"user_{user_id}", f"dataset_{dataset.id}")
            os.makedirs(dest_folder, exist_ok=True)
            shutil.copy(os.path.join(uvl_src_folder, file_name), dest_folder)

            file_path = os.path.join(dest_folder, file_name)

            uvl_file = Hubfile(
                name=file_name,
                checksum=f"checksum{i+1}",
                size=os.path.getsize(file_path),
                feature_model_id=feature_model.id,
            )
            self.seed([uvl_file])

        # ==============================================================================
        # PARTE 2: FORMULA 1 DATASETS
        # ==============================================================================
        formula_src_folder = os.path.join(working_dir, "app", "modules", "dataset", "formula_examples")

        # Destino físico para Formula (donde la app busca los CSVs para previsualizar)
        dest_formula_dir = os.path.join(current_app.root_path, "modules", "dataset", "formula_examples")
        os.makedirs(dest_formula_dir, exist_ok=True)

        if os.path.exists(formula_src_folder):

            all_formula_files = os.listdir(formula_src_folder)
            teams = ["Ferrari", "RedBull", "McLaren", "Mercedes", "AstonMartin", "Williams"]

            for index, team_name in enumerate(teams):
                current_user = user1 if index < 2 else user2  # Alternar usuarios

                # Filtrar CSVs que pertenezcan al equipo (por nombre de archivo)
                team_csv_files = [f for f in all_formula_files if f.endswith(".csv") and team_name.lower() in f.lower()]

                if team_csv_files:
                    # 1. Metadatos
                    ds_meta_data = DSMetaData(
                        deposition_id=None,
                        title=f"{team_name} F1 - Telemetry & Strategy",
                        description=f"Datos oficiales de telemetría y tiempos de {team_name} Racing.",
                        publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
                        publication_doi=f"10.formulahub/{team_name.lower()}-data",
                        dataset_doi=f"10.formulahub/{team_name.lower()}-data",
                        tags=f"f1, {team_name.lower()}, csv",
                    )
                    seeded_ds_meta = self.seed([ds_meta_data])[0]

                    # 2. Autor
                    ds_author = Author(
                        name=f"Data Engineer ({team_name})",
                        affiliation=f"{team_name} F1 Team",
                        ds_meta_data_id=seeded_ds_meta.id,
                    )
                    self.seed([ds_author])

                    # 3. Crear FormulaDataSet
                    formula_dataset = FormulaDataSet(
                        user_id=current_user.id,
                        ds_meta_data_id=seeded_ds_meta.id,
                        created_at=datetime.now(timezone.utc),
                        dataset_type="formula_dataset",
                    )
                    seeded_dataset = self.seed([formula_dataset])[0]

                    # 4. Crear Archivos (FormulaFile)
                    for csv_file in team_csv_files:
                        src_path = os.path.join(formula_src_folder, csv_file)
                        dest_path = os.path.join(dest_formula_dir, csv_file)

                        if not os.path.exists(dest_path):
                            shutil.copy(src_path, dest_path)

                        f_file = FormulaFile(
                            name=csv_file, size=os.path.getsize(dest_path), formula_dataset_id=seeded_dataset.id
                        )
                        self.seed([f_file])
