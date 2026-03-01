from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from app.recrutamento import recrutamento_bp
from app.models import Vaga, Candidato, Candidatura, FaseRecrutamento
from app.extensions import db

@recrutamento_bp.route('/recrutamento/vagas')
@login_required
def listar_vagas():
    # Aqui vamos listar todas as vagas abertas
    return "Módulo de Recrutamento Ativo! 🚀"

