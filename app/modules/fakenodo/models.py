from flask_login import UserMixin

from app import db


class Fakenodo(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    meta_data = db.Column(db.JSON, nullable=False)
    status = db.Column(db.String(100), nullable=False, default="draft")
    doi = db.Column(db.String(250), unique=True, nullable=True)

    def _repr_(self):
        return f"<Fakenodo {self.id}>"
