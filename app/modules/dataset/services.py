import hashlib
import logging
import os
import shutil
import uuid
from typing import Optional

from flask import request

from app.modules.auth.services import AuthenticationService
from app.modules.dataset.models import DataSet, DSMetaData, DSViewRecord, PublicationType, RawDataSet, UVLDataSet
from app.modules.dataset.repositories import (
    AuthorRepository,
    DataSetRepository,
    DOIMappingRepository,
    DSDownloadRecordRepository,
    DSMetaDataRepository,
    DSViewRecordRepository,
)
from app.modules.featuremodel.models import FeatureModel, FMMetaData
from app.modules.featuremodel.repositories import FeatureModelRepository, FMMetaDataRepository
from app.modules.hubfile.models import Hubfile
from app.modules.hubfile.repositories import (
    HubfileRepository,
)
from core.repositories.BaseRepository import BaseRepository
from core.services.BaseService import BaseService

logger = logging.getLogger(__name__)


def calculate_checksum_and_size(file_path):
    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as file:
        content = file.read()
        hash_md5 = hashlib.md5(content).hexdigest()
        return hash_md5, file_size


# === SERVICIO BASE ===
class DataSetService(BaseService):
    def __init__(self):
        super().__init__(DataSetRepository())
        self.dsdownloadrecord_repository = DSDownloadRecordRepository()
        self.dsviewrecord_repostory = DSViewRecordRepository()
        self.author_repository = AuthorRepository()
        self.dsmetadata_repository = DSMetaDataRepository()

    def get_synchronized(self, current_user_id: int) -> DataSet:
        return self.repository.get_synchronized(current_user_id)

    def get_unsynchronized(self, current_user_id: int) -> DataSet:
        return self.repository.get_unsynchronized(current_user_id)

    def get_unsynchronized_dataset(self, current_user_id: int, dataset_id: int) -> DataSet:
        return self.repository.get_unsynchronized_dataset(current_user_id, dataset_id)

    def latest_synchronized(self):
        return self.repository.latest_synchronized()

    def count_synchronized_datasets(self):
        return self.repository.count_synchronized_datasets()

    def count_authors(self) -> int:
        return self.author_repository.count()

    def count_dsmetadata(self) -> int:
        return self.dsmetadata_repository.count()

    def total_dataset_downloads(self) -> int:
        return self.dsdownloadrecord_repository.total_dataset_downloads()

    def total_dataset_views(self) -> int:
        return self.dsviewrecord_repostory.total_dataset_views()

    def update_dsmetadata(self, id, **kwargs):
        return self.dsmetadata_repository.update(id, **kwargs)

    def get_uvlhub_doi(self, dataset: DataSet) -> str:
        domain = os.getenv("DOMAIN", "localhost")
        return f"http://{domain}/doi/{dataset.ds_meta_data.dataset_doi}"

    def create_combined_dataset(self, current_user, title, description, publication_type, tags, source_dataset_ids):
        """
        Crea un nuevo dataset combinando modelos de datasets existentes (carrito).
        """

        # 1. Convertir publication_type (string) a Enum
        try:
            pub_type_enum = PublicationType(publication_type)
        except ValueError:
            pub_type_enum = PublicationType.NONE

        # 2. Crear metadatos del Dataset
        ds_meta = self.dsmetadata_repository.create(
            title=title, description=description, publication_type=pub_type_enum, tags=tags
        )

        # 3. Crear el Dataset (UVLDataSet para soportar feature models)
        # Usamos create con commit=True para obtener el ID necesario para las carpetas
        dataset = UVLDataSet(user_id=current_user.id, ds_meta_data_id=ds_meta.id)
        self.repository.session.add(dataset)
        self.repository.session.commit()

        # 4. Preparar directorios
        working_dir = os.getenv("WORKING_DIR", "")
        dest_folder = os.path.join(working_dir, "uploads", f"user_{current_user.id}", f"dataset_{dataset.id}")
        os.makedirs(dest_folder, exist_ok=True)

        # 5. Iterar datasets fuente y clonar modelos
        for source_id in source_dataset_ids:
            source_ds = self.get_or_404(source_id)

            # Solo procesamos si tiene modelos (es UVLDataSet)
            if hasattr(source_ds, "feature_models"):
                for original_fm in source_ds.feature_models:

                    # A. Clonar FMMetaData
                    original_meta = original_fm.fm_meta_data
                    new_fm_meta = FMMetaData(
                        uvl_filename=original_meta.uvl_filename,
                        title=original_meta.title,
                        description=original_meta.description,
                        publication_type=original_meta.publication_type,
                        publication_doi=original_meta.publication_doi,
                        tags=original_meta.tags,
                        uvl_version=original_meta.uvl_version,
                    )
                    self.repository.session.add(new_fm_meta)
                    self.repository.session.commit()

                    # B. Crear nuevo FeatureModel enlazado al nuevo Dataset
                    new_fm = FeatureModel(data_set_id=dataset.id, fm_meta_data_id=new_fm_meta.id)
                    self.repository.session.add(new_fm)
                    self.repository.session.commit()

                    # C. Clonar Archivos Físicos y crear registro Hubfile
                    for original_file in original_fm.files:
                        # Rutas
                        source_path = os.path.join(
                            working_dir,
                            "uploads",
                            f"user_{source_ds.user_id}",
                            f"dataset_{source_ds.id}",
                            original_file.name,
                        )

                        # Gestión de nombres duplicados
                        dest_path = os.path.join(dest_folder, original_file.name)
                        final_filename = original_file.name

                        if os.path.exists(dest_path):
                            name, ext = os.path.splitext(original_file.name)
                            final_filename = f"{name}_{uuid.uuid4().hex[:4]}{ext}"
                            dest_path = os.path.join(dest_folder, final_filename)
                            # Actualizamos el nombre en metadatos también para mantener consistencia
                            new_fm_meta.uvl_filename = final_filename

                        # Copia física
                        if os.path.exists(source_path):
                            shutil.copy2(source_path, dest_path)

                            # Registro en DB
                            new_file = Hubfile(
                                name=final_filename,
                                checksum=original_file.checksum,
                                size=original_file.size,
                                feature_model_id=new_fm.id,
                            )
                            self.repository.session.add(new_file)
                        else:
                            logger.warning(f"File missing on disk: {source_path}")

        self.repository.session.commit()
        return dataset


# === SERVICIO ESPECÍFICO UVL ===
class UVLDataSetService(DataSetService):
    def __init__(self):
        super().__init__()
        # Inyectamos el repositorio para UVLDataSet
        self.repository = BaseRepository(UVLDataSet)
        self.feature_model_repository = FeatureModelRepository()
        self.fmmetadata_repository = FMMetaDataRepository()
        self.hubfilerepository = HubfileRepository()

    def move_feature_models(self, dataset: UVLDataSet):
        current_user = AuthenticationService().get_authenticated_user()
        source_dir = current_user.temp_folder()
        working_dir = os.getenv("WORKING_DIR", "")
        dest_dir = os.path.join(working_dir, "uploads", f"user_{current_user.id}", f"dataset_{dataset.id}")
        os.makedirs(dest_dir, exist_ok=True)

        for feature_model in dataset.feature_models:
            uvl_filename = feature_model.fm_meta_data.uvl_filename
            shutil.move(os.path.join(source_dir, uvl_filename), dest_dir)

    def count_feature_models(self):
        return self.feature_model_repository.count_feature_models()

    def create_from_form(self, form, current_user) -> UVLDataSet:
        main_author = {
            "name": f"{current_user.profile.surname}, {current_user.profile.name}",
            "affiliation": current_user.profile.affiliation,
            "orcid": current_user.profile.orcid,
        }
        try:
            logger.info(f"Creating dsmetadata...: {form.get_dsmetadata()}")
            dsmetadata = self.dsmetadata_repository.create(**form.get_dsmetadata())
            for author_data in [main_author] + form.get_authors():
                author = self.author_repository.create(commit=False, ds_meta_data_id=dsmetadata.id, **author_data)
                dsmetadata.authors.append(author)

            # Aquí se crea la instancia de UVLDataSet automáticamente gracias al repositorio
            dataset = self.create(commit=False, user_id=current_user.id, ds_meta_data_id=dsmetadata.id)

            for feature_model_form in form.feature_models:
                uvl_filename = feature_model_form.uvl_filename.data
                fmmetadata = self.fmmetadata_repository.create(commit=False, **feature_model_form.get_fmmetadata())
                for author_data in feature_model_form.get_authors():
                    author = self.author_repository.create(commit=False, fm_meta_data_id=fmmetadata.id, **author_data)
                    fmmetadata.authors.append(author)

                fm = self.feature_model_repository.create(
                    commit=False, data_set_id=dataset.id, fm_meta_data_id=fmmetadata.id
                )
                file_path = os.path.join(current_user.temp_folder(), uvl_filename)
                checksum, size = calculate_checksum_and_size(file_path)
                file = self.hubfilerepository.create(
                    commit=False, name=uvl_filename, checksum=checksum, size=size, feature_model_id=fm.id
                )
                fm.files.append(file)

            self.repository.session.commit()
        except Exception as exc:
            logger.info(f"Exception creating dataset from form...: {exc}")
            self.repository.session.rollback()
            raise exc
        return dataset


class RawDataSetService(DataSetService):
    def __init__(self):
        super().__init__()
        self.repository = BaseRepository(RawDataSet)

    def create_from_form(self, form, current_user) -> RawDataSet:
        # Metadatos
        dsmetadata = self.dsmetadata_repository.create(**form.get_dsmetadata())

        # Autor por defecto (el usuario actual)
        author = self.author_repository.create(
            commit=False,
            ds_meta_data_id=dsmetadata.id,
            name=f"{current_user.profile.surname}, {current_user.profile.name}",
            affiliation=current_user.profile.affiliation,
            orcid=current_user.profile.orcid,
        )
        dsmetadata.authors.append(author)

        # Crear RawDataSet
        dataset = self.create(commit=True, user_id=current_user.id, ds_meta_data_id=dsmetadata.id)
        return dataset

    def move_feature_models(self, dataset):
        pass  # No hace nada en Raw


# --- Otros servicios sin cambios ---
class AuthorService(BaseService):
    def __init__(self):
        super().__init__(AuthorRepository())


class DSDownloadRecordService(BaseService):
    def __init__(self):
        super().__init__(DSDownloadRecordRepository())


class DSMetaDataService(BaseService):
    def __init__(self):
        super().__init__(DSMetaDataRepository())

    def update(self, id, **kwargs):
        return self.repository.update(id, **kwargs)

    def filter_by_doi(self, doi: str) -> Optional[DSMetaData]:
        return self.repository.filter_by_doi(doi)


class DSViewRecordService(BaseService):
    def __init__(self):
        super().__init__(DSViewRecordRepository())

    def the_record_exists(self, dataset: DataSet, user_cookie: str):
        return self.repository.the_record_exists(dataset, user_cookie)

    def create_new_record(self, dataset: DataSet, user_cookie: str) -> DSViewRecord:
        return self.repository.create_new_record(dataset, user_cookie)

    def create_cookie(self, dataset: DataSet) -> str:
        user_cookie = request.cookies.get("view_cookie")
        if not user_cookie:
            user_cookie = str(uuid.uuid4())
        existing_record = self.the_record_exists(dataset=dataset, user_cookie=user_cookie)
        if not existing_record:
            self.create_new_record(dataset=dataset, user_cookie=user_cookie)
        return user_cookie


class DOIMappingService(BaseService):
    def __init__(self):
        super().__init__(DOIMappingRepository())

    def get_new_doi(self, old_doi: str) -> str:
        doi_mapping = self.repository.get_new_doi(old_doi)
        return doi_mapping.dataset_doi_new if doi_mapping else None


class SizeService:
    def get_human_readable_size(self, size: int) -> str:
        if size < 1024:
            return f"{size} bytes"
        elif size < 1024**2:
            return f"{round(size / 1024, 2)} KB"
        elif size < 1024**3:
            return f"{round(size / (1024 ** 2), 2)} MB"
        else:
            return f"{round(size / (1024 ** 3), 2)} GB"
