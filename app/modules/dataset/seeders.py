import hashlib
import os
import random
import shutil
from datetime import datetime, timezone

from flask import current_app

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
        # 1. Obtener usuarios
        user1 = User.query.filter_by(email="user1@example.com").first()
        user2 = User.query.filter_by(email="user2@example.com").first()

        if not user1 or not user2:
            print("❌ Error: Usuarios no encontrados.")
            return

        # 2. Rutas
        base_path = os.path.dirname(os.path.abspath(__file__))
        uvl_examples_dir = os.path.join(base_path, "uvl_examples")
        formula_examples_dir = os.path.join(base_path, "formula_examples")

        # Destino físico para Formula (donde la app busca los CSVs para previsualizar)
        dest_formula_dir = os.path.join(current_app.root_path, "modules", "dataset", "formula_examples")
        os.makedirs(dest_formula_dir, exist_ok=True)

        # =======================================================================
        # PARTE A: FORMULA 1 (Solo los 3 archivos existentes)
        # =======================================================================
        print("🏎️  Iniciando Seeding de Fórmula 1...")

        # Nombres exactos de tus archivos
        f_telemetry = "f1_telemetry_spa.csv"
        f_laptimes = "f1_laptimes_monaco.csv"
        f_weather = "f1_weather_silverstone.csv"

        # Comprobar que existen antes de intentar nada
        files_ok = True
        for f in [f_telemetry, f_laptimes, f_weather]:
            if not os.path.exists(os.path.join(formula_examples_dir, f)):
                print(f"❌ Error: No encuentro el archivo físico '{f}' en {formula_examples_dir}")
                files_ok = False

        if files_ok:
            # DATASET 1: Performance Pack (Telemetría + Tiempos)
            self.create_formula_dataset(
                user=user2,
                title="F1 Performance Analysis Pack",
                desc="Contiene telemetría de Spa y tiempos de vuelta de Mónaco.",
                csv_files=[f_telemetry, f_laptimes],
                source_dir=formula_examples_dir,
                dest_dir=dest_formula_dir,
            )

            # DATASET 2: Weather Report (Clima)
            self.create_formula_dataset(
                user=user2,
                title="F1 Weather Report",
                desc="Datos meteorológicos del GP de Gran Bretaña.",
                csv_files=[f_weather],
                source_dir=formula_examples_dir,
                dest_dir=dest_formula_dir,
            )
        else:
            print("⚠️ Saltando creación de F1 por falta de archivos.")

        # =======================================================================
        # PARTE B: UVL (5 Datasets con 2-5 archivos aleatorios cada uno)
        # =======================================================================
        if os.path.exists(uvl_examples_dir):
            uvl_files = [f for f in os.listdir(uvl_examples_dir) if f.endswith(".uvl")]
            uvl_files.sort()

            total_uvl = len(uvl_files)

            if total_uvl >= 2:
                # Crear 5 datasets distintos
                for i in range(1, 6):
                    # Decidir cuántos archivos tendrá este dataset (entre 2 y 5)
                    # Si hay menos de 5 archivos totales, usamos el total como máximo
                    max_files = min(5, total_uvl)
                    num_files_in_dataset = random.randint(2, max_files)

                    # Selección aleatoria sin repetición
                    selected_files = random.sample(uvl_files, num_files_in_dataset)

                    title = f"UVL System Pack {i}"
                    desc = f"Dataset generado automáticamente que contiene {num_files_in_dataset} modelos de características."

                    self.create_uvl_dataset(user1, title, desc, selected_files, uvl_examples_dir)
            else:
                print("⚠️  No hay suficientes archivos .uvl (mínimo 2).")
        else:
            print(f"⚠️  La carpeta {uvl_examples_dir} no existe.")

    def create_formula_dataset(self, user, title, desc, csv_files, source_dir, dest_dir):
        print(f"   -> Creando Dataset F1: '{title}' ({len(csv_files)} archivos)")

        # 1. Metadatos
        ds_meta = DSMetaData(
            title=title,
            description=desc,
            publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
            tags="f1, racing, csv",
            deposition_id=None,
        )
        author = Author(name=f"{user.profile.name} {user.profile.surname}", affiliation="F1 Team")
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

        # 3. Archivos Físicos y BD
        for filename in csv_files:
            # Copiar y renombrar (user_ID_dataset_ID_filename.csv)
            final_filename = f"user_{user.id}_dataset_{dataset.id}_{filename}"

            src_path = os.path.join(source_dir, filename)
            dest_path = os.path.join(dest_dir, final_filename)

            shutil.copy2(src_path, dest_path)

            # Registro en FormulaFile
            f_file = FormulaFile(name=final_filename, size=os.path.getsize(dest_path), formula_dataset_id=dataset.id)
            db.session.add(f_file)

        db.session.commit()

    def create_uvl_dataset(self, user, title, desc, file_names, source_dir):
        print(f"   -> Creando UVL Dataset: '{title}' ({len(file_names)} archivos)")

        # 1. Metadatos
        ds_meta = DSMetaData(
            title=title, description=desc, publication_type=PublicationType.SOFTWARE_DOCUMENTATION, tags="uvl, pack"
        )
        author = Author(name=f"{user.profile.name} {user.profile.surname}", affiliation=user.profile.affiliation)
        ds_meta.authors.append(author)
        db.session.add(ds_meta)
        db.session.commit()

        # 2. Dataset
        dataset = UVLDataSet(
            user_id=user.id,
            ds_meta_data_id=ds_meta.id,
            created_at=datetime.now(timezone.utc),
            dataset_type="uvl_dataset",
        )
        db.session.add(dataset)
        db.session.commit()

        # 3. Directorio Físico
        working_dir = os.getenv("WORKING_DIR", os.getcwd())
        dest_folder = os.path.join(working_dir, "uploads", f"user_{user.id}", f"dataset_{dataset.id}")
        os.makedirs(dest_folder, exist_ok=True)

        # 4. Archivos
        for fname in file_names:
            src_path = os.path.join(source_dir, fname)
            dest_path = os.path.join(dest_folder, fname)

            shutil.copy2(src_path, dest_path)

            # Feature Model Metadata
            fm_meta = FMMetaData(
                uvl_filename=fname,
                title=fname.replace(".uvl", ""),
                description="Imported model",
                publication_type=PublicationType.SOFTWARE_DOCUMENTATION,
                uvl_version="1.0",
            )
            db.session.add(fm_meta)
            db.session.commit()

            # Feature Model
            fm = FeatureModel(uvl_dataset_id=dataset.id, fm_meta_data_id=fm_meta.id)
            db.session.add(fm)
            db.session.commit()

            # Hubfile
            checksum, size = calculate_checksum_and_size(dest_path)
            hubfile = Hubfile(name=fname, checksum=checksum, size=size, feature_model_id=fm.id)
            db.session.add(hubfile)

        db.session.commit()
