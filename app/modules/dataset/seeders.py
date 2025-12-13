import os
import shutil
from datetime import datetime, timezone

from dotenv import load_dotenv

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
        user2 = User.query.filter_by(email="user2@example.com").first()

        if not user1 or not user2:
            print("Error: user1 o user2 no encontrados. Ejecuta primero el seeder de usuarios.")
            return

        # 2. Configurar directorios
        base_path = os.path.dirname(os.path.abspath(__file__))
        src_folder = os.path.join(base_path, "uvl_examples")

        if not os.path.exists(src_folder):
            print(f"Error: La carpeta {src_folder} no existe.")
            return

        load_dotenv()
        working_dir = os.getenv("WORKING_DIR", "")
        if not working_dir:
            working_dir = os.path.abspath(os.getcwd())

        # Listar todos los archivos una vez
        all_files_in_dir = os.listdir(src_folder)

        # 3. Definir los equipos
        teams = ["ferrari", "RedBull", "McLaren", "Mercedes"]

        # 4. Bucle por cada equipo
        for index, team_name in enumerate(teams):

            # --- PREPARACIÓN DEL EQUIPO ---
            current_user = user1 if index < 2 else user2

            # Identificar los archivos .uvl de este equipo
            team_uvl_files = [
                f for f in all_files_in_dir if f.endswith(".uvl") and f.lower().startswith(team_name.lower())
            ]

            if not team_uvl_files:
                print(f"   [SKIP] No hay .uvl para '{team_name}'")
                continue

            # --- REGISTRO DE ARCHIVOS YA ASIGNADOS EN ESTE DATASET ---
            # Esto evita que redbull.jpg se suba 2 veces en el mismo dataset
            assigned_files_in_dataset = set()

            # --- Crear Dataset Contenedor ---
            ds_metrics = DSMetrics(number_of_models=str(len(team_uvl_files)), number_of_features="N/A")
            seeded_ds_metrics = self.seed([ds_metrics])[0]

            ds_meta_data = DSMetaData(
                deposition_id=1 + index,
                title=f"{team_name} F1 Team - Official Data",
                description=f"Datos oficiales de {team_name} incluyendo modelos y documentación técnica.",
                publication_type=PublicationType.DATA_MANAGEMENT_PLAN,
                publication_doi=f"10.formulahub/{team_name.lower().replace(' ', '-')}",
                dataset_doi=f"10.formulahub/{team_name.lower().replace(' ', '-')}",
                tags=f"f1, {team_name.lower()}",
                ds_metrics_id=seeded_ds_metrics.id,
            )
            seeded_ds_meta = self.seed([ds_meta_data])[0]

            ds_author = Author(
                name=f"Head of Aero ({team_name})",
                affiliation=f"{team_name} Racing",
                orcid=f"0000-0001-{team_name.upper().replace(' ', '')[:4]}",
                ds_meta_data_id=seeded_ds_meta.id,
            )
            self.seed([ds_author])

            uvl_dataset = UVLDataSet(
                user_id=current_user.id,
                ds_meta_data_id=seeded_ds_meta.id,
                created_at=datetime.now(timezone.utc),
            )
            seeded_dataset = self.seed([uvl_dataset])[0]

            # Carpeta física destino (única por dataset)
            dest_folder = os.path.join(
                working_dir, "uploads", f"user_{current_user.id}", f"dataset_{seeded_dataset.id}"
            )
            if os.path.exists(dest_folder):
                shutil.rmtree(dest_folder)
            os.makedirs(dest_folder, exist_ok=True)

            # --- Procesar cada modelo UVL ---
            for i, uvl_filename in enumerate(team_uvl_files):
                clean_title = uvl_filename.replace(".uvl", "").replace("_", " ").title()

                fm_meta = FMMetaData(
                    uvl_filename=uvl_filename,
                    title=clean_title,
                    description=f"Modelo {clean_title}",
                    publication_type=PublicationType.SOFTWARE_DOCUMENTATION,
                    publication_doi=f"10.formulahub/{team_name.lower()}-{i}",
                    tags="uvl, model",
                    uvl_version="1.0",
                )
                seeded_meta = self.seed([fm_meta])[0]

                fm_author = Author(
                    name=f"Engineer {i+1}",
                    affiliation=f"{team_name} Team",
                    orcid=f"0000-0000-0000-000{i}",
                    fm_meta_data_id=seeded_meta.id,
                )
                self.seed([fm_author])

                fm = FeatureModel(uvl_dataset_id=seeded_dataset.id, fm_meta_data_id=seeded_meta.id)
                seeded_fm = self.seed([fm])[0]

                # --- LÓGICA DE ASIGNACIÓN DE ARCHIVOS (SIN DUPLICADOS) ---
                current_base_name = os.path.splitext(uvl_filename)[0].lower()

                # Nombres base de los OTROS modelos de este equipo (para no robar sus archivos específicos)
                other_models_bases = [os.path.splitext(f)[0].lower() for f in team_uvl_files if f != uvl_filename]

                files_to_copy = []

                for f in all_files_in_dir:
                    f_lower = f.lower()

                    # 1. Si es el propio UVL actual -> SÍ
                    if f == uvl_filename:
                        files_to_copy.append(f)
                        continue

                    # 2. Si es otro .uvl -> NO (cada mochuelo a su olivo)
                    if f.endswith(".uvl"):
                        continue

                    # 3. Si ya ha sido asignado en este dataset -> NO (evitar duplicados entre modelos)
                    if f in assigned_files_in_dataset:
                        continue

                    # 4. Comprobación Inteligente:
                    # A. ¿Es específico para MÍ? (Empieza por mi nombre base)
                    is_specific_for_me = f_lower.startswith(current_base_name)

                    # B. ¿Es genérico del equipo? (Empieza por equipo... Y NO es específico de otro modelo)
                    #    Ej: "redbull.jpg" empieza por "redbull", y NO empieza por "redbull_rb20" (nombre de otro modelo)
                    is_generic_team_file = f_lower.startswith(team_name.lower()) and not any(
                        f_lower.startswith(other_base) for other_base in other_models_bases
                    )

                    if is_specific_for_me or is_generic_team_file:
                        files_to_copy.append(f)
                        assigned_files_in_dataset.add(f)  # Lo marcamos para que el siguiente modelo no lo coja

                for file_name in files_to_copy:
                    src_path = os.path.join(src_folder, file_name)
                    dest_path = os.path.join(dest_folder, file_name)

                    try:
                        shutil.copy(src_path, dest_path)
                        hubfile = Hubfile(
                            name=file_name,
                            checksum=f"hash_{file_name}_{datetime.now().timestamp()}",
                            size=os.path.getsize(dest_path),
                            feature_model_id=seeded_fm.id,
                        )
                        self.seed([hubfile])
                    except Exception as e:
                        print(f"      [ERROR] Copiando {file_name}: {e}")
