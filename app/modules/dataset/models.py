import os
from datetime import datetime
from enum import Enum

import pandas as pd
from flask import current_app, request
from sqlalchemy import Enum as SQLAlchemyEnum

from app import db


class PublicationType(Enum):
    NONE = "none"
    ANNOTATION_COLLECTION = "annotationcollection"
    BOOK = "book"
    BOOK_SECTION = "section"
    CONFERENCE_PAPER = "conferencepaper"
    DATA_MANAGEMENT_PLAN = "datamanagementplan"
    JOURNAL_ARTICLE = "article"
    PATENT = "patent"
    PREPRINT = "preprint"
    PROJECT_DELIVERABLE = "deliverable"
    PROJECT_MILESTONE = "milestone"
    PROPOSAL = "proposal"
    REPORT = "report"
    SOFTWARE_DOCUMENTATION = "softwaredocumentation"
    TAXONOMIC_TREATMENT = "taxonomictreatment"
    TECHNICAL_NOTE = "technicalnote"
    THESIS = "thesis"
    WORKING_PAPER = "workingpaper"
    OTHER = "other"


class Author(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    affiliation = db.Column(db.String(120))
    orcid = db.Column(db.String(120))
    ds_meta_data_id = db.Column(db.Integer, db.ForeignKey("ds_meta_data.id"))
    fm_meta_data_id = db.Column(db.Integer, db.ForeignKey("fm_meta_data.id"))

    def to_dict(self):
        return {"name": self.name, "affiliation": self.affiliation, "orcid": self.orcid}


class DSMetrics(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number_of_models = db.Column(db.String(120))
    number_of_features = db.Column(db.String(120))

    def __repr__(self):
        return f"DSMetrics<models={self.number_of_models}, features={self.number_of_features}>"


class DSMetaData(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    deposition_id = db.Column(db.Integer)
    title = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=False)
    publication_type = db.Column(SQLAlchemyEnum(PublicationType), nullable=False)
    publication_doi = db.Column(db.String(120))
    dataset_doi = db.Column(db.String(120))
    tags = db.Column(db.String(120))
    ds_metrics_id = db.Column(db.Integer, db.ForeignKey("ds_metrics.id"))
    ds_metrics = db.relationship("DSMetrics", uselist=False, backref="ds_meta_data", cascade="all, delete")
    authors = db.relationship("Author", backref="ds_meta_data", lazy=True, cascade="all, delete")


# ==========================================
# CLASE PADRE: DataSet
# ==========================================
class DataSet(db.Model):
    __tablename__ = "data_set"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    ds_meta_data_id = db.Column(db.Integer, db.ForeignKey("ds_meta_data.id"), nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    download_count = db.Column(db.Integer, nullable=False, default=0, server_default="0")

    # --- POLIMORFISMO ---
    dataset_type = db.Column(db.String(50))

    __mapper_args__ = {"polymorphic_identity": "generic_dataset", "polymorphic_on": dataset_type}

    ds_meta_data = db.relationship("DSMetaData", backref=db.backref("data_set", uselist=False))

    def name(self):
        return self.ds_meta_data.title

    def delete(self):
        db.session.delete(self)
        db.session.commit()

    def get_cleaned_publication_type(self):
        return self.ds_meta_data.publication_type.name.replace("_", " ").title()

    def get_zenodo_url(self):
        return f"https://zenodo.org/record/{self.ds_meta_data.deposition_id}" if self.ds_meta_data.dataset_doi else None

    def get_uvlhub_doi(self):
        from app.modules.dataset.services import DataSetService

        return DataSetService().get_uvlhub_doi(self)

    # --- Métodos que las hijas deben sobreescribir ---
    def files(self):
        return []

    def get_files_count(self):
        return 0

    def get_file_total_size(self):
        return 0

    def get_file_total_size_for_human(self):
        from app.modules.dataset.services import SizeService

        return SizeService().get_human_readable_size(self.get_file_total_size())

    def get_dashboard_template(self):
        """Devuelve el HTML parcial para pintar los detalles específicos"""
        return "dataset/types/generic_details.html"

    def to_dict(self):
        return {
            "title": self.ds_meta_data.title,
            "id": self.id,
            "created_at": self.created_at,
            "created_at_timestamp": int(self.created_at.timestamp()),
            "description": self.ds_meta_data.description,
            "authors": [author.to_dict() for author in self.ds_meta_data.authors],
            "publication_type": self.get_cleaned_publication_type(),
            "publication_doi": self.ds_meta_data.publication_doi,
            "dataset_doi": self.ds_meta_data.dataset_doi,
            "tags": self.ds_meta_data.tags.split(",") if self.ds_meta_data.tags else [],
            "url": self.get_uvlhub_doi() if self.ds_meta_data.dataset_doi else f"/dataset/view/{self.id}",
            "download": f'{request.host_url.rstrip("/")}/dataset/download/{self.id}',
            "zenodo": self.get_zenodo_url(),
            "download_count": self.download_count,
            "dataset_type": self.dataset_type,
        }

    def __repr__(self):
        return f"DataSet<{self.id}>"


# ==========================================
# CLASE HIJA: UVLDataSet
# ==========================================
class UVLDataSet(DataSet):
    __tablename__ = "uvl_dataset"

    id = db.Column(db.Integer, db.ForeignKey("data_set.id"), primary_key=True)

    feature_models = db.relationship("FeatureModel", backref="uvl_dataset", lazy=True, cascade="all, delete")

    __mapper_args__ = {
        "polymorphic_identity": "uvl_dataset",
    }

    def files(self):
        return [file for fm in self.feature_models for file in fm.files]

    def get_files_count(self):
        return sum(len(fm.files) for fm in self.feature_models)

    def get_file_total_size(self):
        return sum(file.size for fm in self.feature_models for file in fm.files)

    def get_dashboard_template(self):
        return "dataset/types/uvl_details.html"

    def to_dict(self):
        data = super().to_dict()
        data.update(
            {
                "files": [file.to_dict() for fm in self.feature_models for file in fm.files],
                "files_count": self.get_files_count(),
                "total_size_in_bytes": self.get_file_total_size(),
                "total_size_in_human_format": self.get_file_total_size_for_human(),
            }
        )
        return data


# ==========================================
# Clase Auxiliar -> FormulaFile (Para los CSV) (Lo que sería FeatureModel + Hubfile en UVL)
# ==========================================
class FormulaFile(db.Model):
    __tablename__ = "formula_file"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    size = db.Column(db.Integer, nullable=True)
    formula_dataset_id = db.Column(db.Integer, db.ForeignKey("formula_dataset.id"), nullable=False)

    def get_path(self):
        """
        Calcula la ruta física dinámica.
        """
        ds = self.dataset

        working_dir = os.getenv("WORKING_DIR") or os.path.abspath(os.getcwd())
        upload_path = os.path.join(working_dir, "uploads", f"user_{ds.user_id}", f"dataset_{ds.id}", self.name)

        if os.path.exists(upload_path):
            return upload_path

        seed_path = os.path.join(current_app.root_path, "modules", "dataset", "formula_examples", self.name)
        return seed_path

    def to_dict(self):
        return {"id": self.id, "name": self.name, "size": self.size, "url": f"/dataset/formula/file_preview/{self.id}"}


# ==========================================
# CLASE HIJA: FormulaDataSet
# ==========================================
class FormulaDataSet(DataSet):
    __tablename__ = "formula_dataset"
    id = db.Column(db.Integer, db.ForeignKey("data_set.id"), primary_key=True)

    files_rel = db.relationship("FormulaFile", backref="dataset", cascade="all, delete-orphan")

    __mapper_args__ = {
        "polymorphic_identity": "formula_dataset",
    }

    def files(self):
        return self.files_rel

    def get_files_count(self):
        return len(self.files_rel)

    def get_file_total_size(self):
        return sum(f.size for f in self.files_rel if f.size)

    def get_dashboard_template(self):
        return "dataset/types/formula_details.html"

    def to_dict(self):
        data = super().to_dict()
        data.update(
            {
                "files": [f.to_dict() for f in self.files_rel],
                "files_count": self.get_files_count(),
                "total_size_in_bytes": self.get_file_total_size(),
                "total_size_in_human_format": self.get_file_total_size_for_human(),
            }
        )
        return data

    def get_preview_html(self):
        """
        Lee el PRIMER CSV usando PANDAS y devuelve HTML.
        """
        if not self.files_rel:  # OJO: Usar self.files_rel
            return "<p>No CSV files in this dataset.</p>"

        first_file = self.files_rel[0]
        file_path = first_file.get_path()

        if not os.path.exists(file_path):
            return f"<p class='text-danger'>File {first_file.name} not found on disk at {file_path}.</p>"

        try:
            df = pd.read_csv(file_path, nrows=10)
            return df.to_html(classes="table table-striped table-sm table-hover", index=False)

        except Exception as e:
            return f"<div class='alert alert-danger'>Error reading CSV with Pandas: {str(e)}</div>"


# ==========================================
# CLASE HIJA: RawDataSet
# ==========================================
class RawDataSet(DataSet):
    __tablename__ = "raw_dataset"
    id = db.Column(db.Integer, db.ForeignKey("data_set.id"), primary_key=True)

    __mapper_args__ = {
        "polymorphic_identity": "raw_dataset",
    }


class DSDownloadRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("data_set.id"))
    download_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    download_cookie = db.Column(db.String(36), nullable=False)


class DSViewRecord(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=True)
    dataset_id = db.Column(db.Integer, db.ForeignKey("data_set.id"))
    view_date = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    view_cookie = db.Column(db.String(36), nullable=False)


class DOIMapping(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    dataset_doi_old = db.Column(db.String(120))
    dataset_doi_new = db.Column(db.String(120))
