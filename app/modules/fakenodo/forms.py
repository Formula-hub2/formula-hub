from flask_wtf import FlaskForm
from wtforms import SubmitField


class Fakenodo(FlaskForm):
    submit = SubmitField("Submit")