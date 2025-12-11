import os
import re
import shutil
from datetime import datetime, timezone

from dotenv import load_dotenv

from app import db
from app.modules.auth.models import User
from app.modules.dataset.models import Author, DSMetaData, DSMetrics, PublicationType, UVLDataSet
from app.modules.featuremodel.models import FeatureModel, FMMetaData
from app.modules.hubfile.models import Hubfile
from core.seeders.BaseSeeder import BaseSeeder


class DataSetSeeder(BaseSeeder):
    priority = 2

    def run(self):
        # 1. Recuperar Usuarios
        user1 = User.query.filter_by(email="user1@example.com").first()
        # user2 = User.query.filter_by(email="user2@example.com").first()

        # Si no existen usuarios, creamos user1 de emergencia para que no falle
        if not user1:
            print("Warning: user1 no encontrado. Creando usuario dummy...")
            user1 = User(email="user1@example.com", password="password", created_at=datetime.now(timezone.utc))
            db.session.add(user1)
            db.session.commit()

        # 2. Preparar carpetas
        base_path = os.path.dirname(os.path.abspath(__file__))
        src_folder = os.path.join(base_path, "uvl_examples")

        if not os.path.exists(src_folder):
            print(f"Error: La carpeta {src_folder} no existe.")
            return

        # Escaneo dinámico (SIN nombres fijos)
        # Excluye los archivos de ejemplo (file1.uvl, ..., file12.uvl)
        files_in_dir = os.listdir(src_folder)
        uvl_files = [f for f in files_in_dir if f.endswith(".uvl") and not re.match(r"^file\d+\.uvl$", f)]

        # Impide crear un dataset sin archivos .uvl (PODRIA MODIFICARSE)
        if not uvl_files:
            print(f"No hay archivos .uvl en la carpeta {src_folder}.")
            return

        # 3. Crear Dataset Contenedor
        ds_metrics = DSMetrics(number_of_models=str(len(uvl_files)), number_of_features="N/A")
        seeded_ds_metrics = self.seed([ds_metrics])[0]

        ds_meta_data = DSMetaData(
            deposition_id=1,
            title="Formula 1 2024 - Official Data",
            description="Dataset técnico con especificaciones (.pdf), telemetría (.csv) y modelos (.uvl).",
            publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
            publication_doi="10.formulahub/f1-multi",
            dataset_doi="10.formulahub/f1-multi",
            tags="f1, telemetry, specs",
            ds_metrics_id=seeded_ds_metrics.id,
        )
        seeded_ds_meta = self.seed([ds_meta_data])[0]

        ds_author = Author(
            name="FIA Technical Delegate",
            affiliation="Federation Internationale de l'Automobile",
            orcid="0000-0001-FIA-TECH",
            ds_meta_data_id=seeded_ds_meta.id,
        )
        self.seed([ds_author])

        f1_dataset = UVLDataSet(
            user_id=user1.id,
            ds_meta_data_id=seeded_ds_meta.id,
            created_at=datetime.now(timezone.utc),
        )
        seeded_dataset = self.seed([f1_dataset])[0]

        # 4. Procesar archivos
        load_dotenv()
        working_dir = os.getenv("WORKING_DIR", "")
        if not working_dir:
            working_dir = os.path.abspath(os.getcwd())

        dest_folder = os.path.join(working_dir, "uploads", f"user_{user1.id}", f"dataset_{seeded_dataset.id}")

        if os.path.exists(dest_folder):
            shutil.rmtree(dest_folder)
        os.makedirs(dest_folder, exist_ok=True)

        for i, uvl_filename in enumerate(uvl_files):
            clean_title = uvl_filename.replace(".uvl", "").replace("_", " ").title()

            fm_meta = FMMetaData(
                uvl_filename=uvl_filename,
                title=clean_title,
                description=f"Paquete técnico completo para {clean_title}",
                publication_type=PublicationType.SOFTWARE_DOCUMENTATION,
                publication_doi=f"10.formulahub/model-{i}",
                tags="chassis, aero, data",
                uvl_version="1.0",
            )
            seeded_meta = self.seed([fm_meta])[0]

            author = Author(
                name="Team Engineer",
                affiliation="F1 Team",
                orcid=f"0000-0000-0000-000{i}",
                fm_meta_data_id=seeded_meta.id,
            )
            self.seed([author])

            fm = FeatureModel(uvl_dataset_id=seeded_dataset.id, fm_meta_data_id=seeded_meta.id)
            seeded_fm = self.seed([fm])[0]

            # Copiar archivos
            base_name = os.path.splitext(uvl_filename)[0]
            all_files = os.listdir(src_folder)
            related_files = [f for f in all_files if f.startswith(base_name)]

            for file_name in related_files:
                src_path = os.path.join(src_folder, file_name)
                dest_path = os.path.join(dest_folder, file_name)

                try:
                    shutil.copy(src_path, dest_path)
                    hubfile = Hubfile(
                        name=file_name,
                        checksum=f"hash_{file_name}",
                        size=os.path.getsize(dest_path),
                        feature_model_id=seeded_fm.id,
                    )
                    self.seed([hubfile])
                except Exception as e:
                    print(f"Error copiando {file_name}: {e}")
                    continue
