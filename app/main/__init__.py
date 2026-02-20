from flask import Blueprint

# O parâmetro template_folder='templates' diz ao Flask para procurar 
# os arquivos dentro de app/main/templates/
main_bp = Blueprint('main', __name__, template_folder='templates')

# Importamos as rotas no final para evitar o erro de importação circular
from app.main import routes

