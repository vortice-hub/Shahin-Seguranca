from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.recrutamento import recrutamento_bp
from app.models import Vaga, Candidato, Candidatura, FaseRecrutamento
from app.extensions import db

@recrutamento_bp.route('/vagas', methods=['GET'])
@login_required
def dashboard_vagas():
    # Busca todas as vagas ativas da empresa do usuário logado
    vagas = Vaga.query.filter_by(empresa_id=current_user.empresa_id).order_by(Vaga.id.desc()).all()
    return render_template('recrutamento/dashboard_ats.html', vagas=vagas)

@recrutamento_bp.route('/vagas/nova', methods=['POST'])
@login_required
def nova_vaga():
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

