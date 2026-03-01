import os
import uuid
from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from google.cloud import storage

from app.recrutamento import recrutamento_bp
from app.models import Vaga, Candidato, Candidatura, FaseRecrutamento
from app.extensions import db

# ==============================================================================
# 🎯 VORTICE RECRUTAMENTO - GESTÃO DE VAGAS E ATS
# ==============================================================================

@recrutamento_bp.route('/vagas', methods=['GET'])
@login_required
def dashboard_vagas():
    """Exibe o painel principal com todas as vagas abertas do cliente."""
    vagas = Vaga.query.filter_by(empresa_id=current_user.empresa_id).order_by(Vaga.id.desc()).all()
    return render_template('recrutamento/dashboard_ats.html', vagas=vagas)

@recrutamento_bp.route('/vagas/nova', methods=['POST'])
@login_required
def nova_vaga():
    """Cria uma nova vaga e gera automaticamente as colunas do Kanban."""
    titulo = request.form.get('titulo')
    descricao = request.form.get('descricao')
    local = request.form.get('local')
    salario = request.form.get('salario')
    
    # 1. Cria a vaga no banco de dados
    nova_vaga = Vaga(
        titulo=titulo,
        descricao=descricao,
        local=local,
        salario=salario,
        empresa_id=current_user.empresa_id
    )
    db.session.add(nova_vaga)
    db.session.commit() # Salva para gerar o ID da vaga
    
    # 2. Cria automaticamente o Funil Kanban padrão para esta vaga
    fases_padrao = ["Novos Currículos", "Triagem", "Entrevista", "Aprovados"]
    for i, nome_fase in enumerate(fases_padrao):
        fase = FaseRecrutamento(
            vaga_id=nova_vaga.id, 
            nome=nome_fase, 
            ordem=i, 
            empresa_id=current_user.empresa_id
        )
        db.session.add(fase)
        
    db.session.commit()
    
    flash('Nova vaga criada com sucesso! O funil de seleção já está pronto.', 'success')
    return redirect(url_for('recrutamento.dashboard_vagas'))

# ==============================================================================
# 🗄️ VORTICE RECRUTAMENTO - BANCO DE TALENTOS E CURRÍCULOS
# ==============================================================================

@recrutamento_bp.route('/banco-talentos', methods=['GET'])
@login_required
def banco_talentos():
    """Lista todos os candidatos guardados no banco de dados da empresa."""
    candidatos = Candidato.query.filter_by(empresa_id=current_user.empresa_id).order_by(Candidato.id.desc()).all()
    return render_template('recrutamento/banco_talentos.html', candidatos=candidatos)

@recrutamento_bp.route('/banco-talentos/novo', methods=['POST'])
@login_required
def novo_candidato():
    """Cadastra um novo candidato fazendo upload do currículo para o GCP Storage."""
    nome = request.form.get('nome')
    email = request.form.get('email')
    telefone = request.form.get('telefone')
    tags = request.form.get('palavras_chave')
    
    arquivo_cv = request.files.get('arquivo_cv')
    url_cv = None
    
    # ☁️ Lógica de Upload Profissional para o Google Cloud Storage
    if arquivo_cv and arquivo_cv.filename:
        bucket_name = os.environ.get('VORTICE_BUCKET')
        
        if not bucket_name:
            flash('Erro de infraestrutura: Variável VORTICE_BUCKET não está configurada.', 'error')
            return redirect(url_for('recrutamento.banco_talentos'))
            
        try:
            # 1. Gera um nome de arquivo único e isolado por Tenant (Inquilino)
            filename = secure_filename(arquivo_cv.filename)
            extensao = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'pdf'
            nome_hash = uuid.uuid4().hex
            
            # Caminho no Storage: cvs/{id_da_empresa}/{hash}.pdf
            caminho_gcp = f"cvs/{current_user.empresa_id}/{nome_hash}.{extensao}"
            
            # 2. Conecta ao GCP e faz o upload direto da memória (sem salvar local)
            storage_client = storage.Client()
            bucket = storage_client.bucket(bucket_name)
            blob = bucket.blob(caminho_gcp)
            
            blob.upload_from_file(arquivo_cv, content_type=arquivo_cv.content_type)
            
            # 3. Retorna a URL pública do currículo
            url_cv = blob.public_url
            
        except Exception as e:
            flash(f'Falha ao enviar documento para a nuvem: {str(e)}', 'error')
            return redirect(url_for('recrutamento.banco_talentos'))
    
    # Cria o registro no banco de dados com a URL em nuvem
    novo_cand = Candidato(
        nome=nome,
        email=email,
        telefone=telefone,
        palavras_chave=tags,
        url_curriculo=url_cv,
        empresa_id=current_user.empresa_id
    )
    
    db.session.add(novo_cand)
    db.session.commit()
    
    flash(f'O currículo de {nome} foi guardado no banco com sucesso!', 'success')
    return redirect(url_for('recrutamento.banco_talentos'))

