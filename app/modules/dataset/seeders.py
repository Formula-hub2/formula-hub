import hashlib
import os
import random
import shutil
from datetime import datetime, timezone

from app import db
from app.modules.auth.models import User
from app.modules.dataset.models import Author, DSMetaData, FormulaDataSet, FormulaFile, PublicationType, UVLDataSet
from app.modules.featuremodel.models import FeatureModel, FMMetaData
from app.modules.hubfile.models import Hubfile
from core.seeders.BaseSeeder import BaseSeeder


def calculate_checksum_and_size(file_path):
    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as file:
        content = file.read()
    hash_md5 = hashlib.md5(content, usedforsecurity=False).hexdigest()
    return hash_md5, file_size


class DataSetSeeder(BaseSeeder):
    priority = 2

    def run(self):
        user1 = User.query.filter_by(email="user1@example.com").first()
        user2 = User.query.filter_by(email="user2@example.com").first()

        if not user1 or not user2:
            print("❌ Error: Usuarios no encontrados.")
            return

        base_path = os.path.dirname(os.path.abspath(__file__))
        uvl_examples_dir = os.path.join(base_path, "uvl_examples")
        formula_examples_dir = os.path.join(base_path, "formula_examples")

        files_pack_1 = ["f1_telemetry_spa.csv", "f1_laptimes_monaco.csv"]
        files_pack_2 = ["f1_weather_silverstone.csv"]

        # Verificamos que existen físicamente antes de registrar en BD
        if all(os.path.exists(os.path.join(formula_examples_dir, f)) for f in files_pack_1 + files_pack_2):

            # DATASET 1
            self.create_formula_dataset_entry(
                user=user2,
                title="F1 Performance Analysis Pack",
                desc="Contiene telemetría de Spa y tiempos de vuelta de Mónaco.",
                filenames=files_pack_1,
                source_dir=formula_examples_dir,
            )

            # DATASET 2
            self.create_formula_dataset_entry(
                user=user2,
                title="F1 Weather Report",
                desc="Datos meteorológicos del GP de Gran Bretaña.",
                filenames=files_pack_2,
                source_dir=formula_examples_dir,
            )
        else:
            print(f"❌ No encuentro tus archivos CSV en {formula_examples_dir}. Asegúrate de que están creados.")

        if os.path.exists(uvl_examples_dir):
            uvl_files = [f for f in os.listdir(uvl_examples_dir) if f.endswith(".uvl")]
            uvl_files.sort()

            if len(uvl_files) >= 2:
                for i in range(1, 6):  # 5 Datasets
                    max_files = min(5, len(uvl_files))
                    num = random.randint(2, max_files)
                    selected = random.sample(uvl_files, num)

                    self.create_uvl_dataset(
                        user1, f"UVL System Pack {i}", "Dataset generado.", selected, uvl_examples_dir
                    )

    def create_formula_dataset_entry(self, user, title, desc, filenames, source_dir):
        """
        Crea SOLO las entradas en la base de datos apuntando a los archivos existentes.
        NO copia ni renombra archivos físicos.
        """
        print(f"   -> Registrando Dataset F1: '{title}'")

        # 1. Metadata
        ds_meta = DSMetaData(
            title=title,
            description=desc,
            publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
            tags="f1, csv",
            deposition_id=None,
        )
        author = Author(name=f"{user.profile.name}", affiliation="F1 Team")
        ds_meta.authors.append(author)
        db.session.add(ds_meta)
        db.session.commit()

        # 2. Dataset
        dataset = FormulaDataSet(
            user_id=user.id,
            ds_meta_data_id=ds_meta.id,
            created_at=datetime.now(timezone.utc),
            dataset_type="formula_dataset",
        )
        db.session.add(dataset)
        db.session.commit()

        # 3. Archivos (FormulaFile)
        for fname in filenames:
            file_path = os.path.join(source_dir, fname)

            # Calculamos tamaño real del archivo existente
            size = os.path.getsize(file_path)

            # Insertamos en BD apuntando al nombre original
            f_file = FormulaFile(
                name=fname,
                size=size,
                formula_dataset_id=dataset.id,
            )
            db.session.add(f_file)

        db.session.commit()

    def create_uvl_dataset(self, user, title, desc, file_names, source_dir):
        ds_meta = DSMetaData(
            title=title, description=desc, publication_type=PublicationType.SOFTWARE_DOCUMENTATION, tags="uvl"
        )
        author = Author(name=f"{user.profile.name}", affiliation="Home")
        ds_meta.authors.append(author)
        db.session.add(ds_meta)
        db.session.commit()

        dataset = UVLDataSet(
            user_id=user.id,
            ds_meta_data_id=ds_meta.id,
            created_at=datetime.now(timezone.utc),
            dataset_type="uvl_dataset",
        )
        db.session.add(dataset)
        db.session.commit()

        working_dir = os.getenv("WORKING_DIR", os.getcwd())
        dest_folder = os.path.join(working_dir, "uploads", f"user_{user.id}", f"dataset_{dataset.id}")
        os.makedirs(dest_folder, exist_ok=True)

        for fname in file_names:
            src_path = os.path.join(source_dir, fname)
            dest_path = os.path.join(dest_folder, fname)
            shutil.copy2(src_path, dest_path)

            fm_meta = FMMetaData(
                uvl_filename=fname,
                title=fname,
                description="Auto",
                publication_type=PublicationType.SOFTWARE_DOCUMENTATION,
                uvl_version="1.0",
            )
            db.session.add(fm_meta)
            db.session.commit()

            fm = FeatureModel(uvl_dataset_id=dataset.id, fm_meta_data_id=fm_meta.id)
            db.session.add(fm)
            db.session.commit()

            checksum, size = calculate_checksum_and_size(dest_path)
            hubfile = Hubfile(name=fname, checksum=checksum, size=size, feature_model_id=fm.id)
            db.session.add(hubfile)

        db.session.commit()
