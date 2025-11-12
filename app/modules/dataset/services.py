import hashlib
import logging
import os
import shutil
import uuid
from typing import Optional

from flask import request

from app.modules.auth.services import AuthenticationService
from app.modules.dataset.models import DataSet, DSMetaData, DSViewRecord, PublicationType
from app.modules.dataset.repositories import (
    AuthorRepository,
    DataSetRepository,
    DOIMappingRepository,
    DSDownloadRecordRepository,
    DSMetaDataRepository,
    DSViewRecordRepository,
)
from app.modules.featuremodel.repositories import FeatureModelRepository, FMMetaDataRepository
from app.modules.hubfile.repositories import (
    HubfileDownloadRecordRepository,
    HubfileRepository,
    HubfileViewRecordRepository,
)
from core.services.BaseService import BaseService

logger = logging.getLogger(__name__)


def calculate_checksum_and_size(file_path):
    file_size = os.path.getsize(file_path)
    with open(file_path, "rb") as file:
        content = file.read()
        hash_md5 = hashlib.md5(content).hexdigest()
        return hash_md5, file_size


class DataSetService(BaseService):
    def __init__(self):
        super().__init__(DataSetRepository())
        self.feature_model_repository = FeatureModelRepository()
        self.author_repository = AuthorRepository()
        self.dsmetadata_repository = DSMetaDataRepository()
        self.fmmetadata_repository = FMMetaDataRepository()
        self.dsdownloadrecord_repository = DSDownloadRecordRepository()
        self.hubfiledownloadrecord_repository = HubfileDownloadRecordRepository()
        self.hubfilerepository = HubfileRepository()
        self.dsviewrecord_repostory = DSViewRecordRepository()
        self.hubfileviewrecord_repository = HubfileViewRecordRepository()

    def move_feature_models(self, dataset: DataSet):
        current_user = AuthenticationService().get_authenticated_user()
        source_dir = current_user.temp_folder()

        working_dir = os.getenv("WORKING_DIR", "")
        dest_dir = os.path.join(working_dir, "uploads", f"user_{current_user.id}", f"dataset_{dataset.id}")

        os.makedirs(dest_dir, exist_ok=True)

        for feature_model in dataset.feature_models:
            uvl_filename = feature_model.fm_meta_data.uvl_filename
            shutil.move(os.path.join(source_dir, uvl_filename), dest_dir)

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

    def count_feature_models(self):
        return self.feature_model_service.count_feature_models()

    def count_authors(self) -> int:
        return self.author_repository.count()

    def count_dsmetadata(self) -> int:
        return self.dsmetadata_repository.count()

    def total_dataset_downloads(self) -> int:
        return self.dsdownloadrecord_repository.total_dataset_downloads()

    def total_dataset_views(self) -> int:
        return self.dsviewrecord_repostory.total_dataset_views()

    def create_from_form(self, form, current_user) -> DataSet:
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

            dataset = self.create(commit=False, user_id=current_user.id, ds_meta_data_id=dsmetadata.id)

            for feature_model in form.feature_models:
                uvl_filename = feature_model.uvl_filename.data
                fmmetadata = self.fmmetadata_repository.create(commit=False, **feature_model.get_fmmetadata())
                for author_data in feature_model.get_authors():
                    author = self.author_repository.create(commit=False, fm_meta_data_id=fmmetadata.id, **author_data)
                    fmmetadata.authors.append(author)

                fm = self.feature_model_repository.create(
                    commit=False, data_set_id=dataset.id, fm_meta_data_id=fmmetadata.id
                )

                # associated files in feature model
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

    def update_dsmetadata(self, id, **kwargs):
        return self.dsmetadata_repository.update(id, **kwargs)

    def get_uvlhub_doi(self, dataset: DataSet) -> str:
        domain = os.getenv("DOMAIN", "localhost")
        return f"http://{domain}/doi/{dataset.ds_meta_data.dataset_doi}"
    
    def create_combined_dataset(self, current_user, title, description, publication_type, tags, source_dataset_ids):
        """Crea un nuevo dataset combinando modelos de datasets existentes"""
    
        logger.info(f"Creating combined dataset: {title}")
        
        main_author = {
            "name": f"{current_user.profile.surname}, {current_user.profile.name}",
            "affiliation": current_user.profile.affiliation,
            "orcid": current_user.profile.orcid,
        }
        
        try:
            # Convertir publication_type string a enum
            publication_type_enum = PublicationType.NONE
            if publication_type and publication_type != "any":
                for pt in PublicationType:
                    if pt.value == publication_type:
                        publication_type_enum = pt
                        break
            
            # Crear metadata del dataset
            dsmetadata_data = {
                "title": title,
                "description": description,
                "publication_type": publication_type_enum,
                "publication_doi": None,
                "dataset_doi": None,
                "deposition_id": None,
                "tags": tags
            }
            

            dsmetadata = self.dsmetadata_repository.create(**dsmetadata_data)
            
            # Añadir autor principal
            author = self.author_repository.create(
                commit=False, 
                ds_meta_data_id=dsmetadata.id, 
                **main_author
            )
            dsmetadata.authors.append(author)
            
            # Crear el dataset
            dataset = self.create(commit=False, user_id=current_user.id, ds_meta_data_id=dsmetadata.id)
            
            # Crear directorio para el nuevo dataset
            working_dir = os.getenv("WORKING_DIR", "")
            new_dataset_dir = os.path.join(working_dir, "uploads", f"user_{current_user.id}", f"dataset_{dataset.id}")
            os.makedirs(new_dataset_dir, exist_ok=True)
            
            # Copiar feature models de los datasets seleccionados
            feature_models_copied = 0
            for source_dataset_id in source_dataset_ids:
                source_dataset = self.get_or_404(source_dataset_id)
                
                # Obtener directorio del dataset fuente
                source_dataset_dir = os.path.join(working_dir, "uploads", f"user_{source_dataset.user_id}", f"dataset_{source_dataset.id}")
                
                for feature_model in source_dataset.feature_models:
                    
                    # Crear nueva metadata para el feature model
                    fmmetadata_data = {
                        "uvl_filename": feature_model.fm_meta_data.uvl_filename,
                        "title": feature_model.fm_meta_data.title or feature_model.fm_meta_data.uvl_filename,
                        "description": feature_model.fm_meta_data.description or "",
                        "publication_type": feature_model.fm_meta_data.publication_type or PublicationType.NONE,
                        "publication_doi": feature_model.fm_meta_data.publication_doi,
                        "tags": feature_model.fm_meta_data.tags,
                        "uvl_version": feature_model.fm_meta_data.uvl_version or "1.0",
                    }
                    
                    fmmetadata = self.fmmetadata_repository.create(commit=False, **fmmetadata_data)
                
                    # Copiar autores del feature model original
                    for original_author in feature_model.fm_meta_data.authors:
                        author_data = original_author.to_dict()
                        author = self.author_repository.create(
                            commit=False, 
                            fm_meta_data_id=fmmetadata.id, 
                            **author_data
                        )
                        fmmetadata.authors.append(author)
                    
                    # Crear el feature model en el nuevo dataset
                    fm = self.feature_model_repository.create(
                        commit=False, 
                        data_set_id=dataset.id, 
                        fm_meta_data_id=fmmetadata.id
                    )
                    
                    # COPIAR LOS ARCHIVOS uvl
                    files_copied = 0
                    for file in feature_model.files:
                        # Ruta del archivo original
                        source_file_path = os.path.join(source_dataset_dir, file.name)
                        
                        # Ruta del archivo destino
                        dest_file_path = os.path.join(new_dataset_dir, file.name)
                        
                        # Verificar que el archivo fuente existe
                        if os.path.exists(source_file_path):
                            # Copiar el archivo
                            shutil.copy2(source_file_path, dest_file_path)
                            
                            # Recalcular checksum y tamaño del archivo copiado
                            new_checksum, new_size = calculate_checksum_and_size(dest_file_path)
                            
                            # Crear registro del archivo con los nuevos datos
                            new_file = self.hubfilerepository.create(
                                commit=False, 
                                name=file.name, 
                                checksum=new_checksum, 
                                size=new_size, 
                                feature_model_id=fm.id
                            )
                            fm.files.append(new_file)
                            files_copied += 1
                        else:
                            logger.error(f"Source file not found: {source_file_path}")
                    
                    feature_models_copied += 1
            
            logger.info(f"Total feature models copied: {feature_models_copied}")
            
            # Hacer commit final
            self.repository.session.commit()
            return dataset
            
        except Exception as exc:
            logger.error(f"=== ERROR in create_combined_dataset ===")
            self.repository.session.rollback()
            raise exc

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
        if doi_mapping:
            return doi_mapping.dataset_doi_new
        else:
            return None


class SizeService:

    def __init__(self):
        pass

    def get_human_readable_size(self, size: int) -> str:
        if size < 1024:
            return f"{size} bytes"
        elif size < 1024**2:
            return f"{round(size / 1024, 2)} KB"
        elif size < 1024**3:
            return f"{round(size / (1024 ** 2), 2)} MB"
        else:
            return f"{round(size / (1024 ** 3), 2)} GB"
