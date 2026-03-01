from flask import Blueprint

recrutamento_bp = Blueprint('recrutamento', __name__, template_folder='templates')

from . import routes

