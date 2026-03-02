import os
import uuid
import json
import io
from flask import render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from google.cloud import storage

from app.recrutamento import recrutamento_bp
from app.models import Vaga, Candidato, Candidatura, FaseRecrutamento, TagCandidato
from app.extensions import db

# IMPORTANTE: Importar o nosso motor de IA
from app.services.cv_parser import analisar_curriculo_ia

# ==============================================================================
# 🎯 VORTICE RECRUTAMENTO - GESTÃO DE VAGAS E ATS
# ==============================================================================

@recrutamento_bp.route('/vagas', methods=['GET'])
@login_required
def dashboard_vagas():
    vagas = Vaga.query.filter_by(empresa_id=current_user.empresa_id).order_by(Vaga.id.desc()).all()
    return render_template('recrutamento/dashboard_ats.html', vagas=vagas)

@recrutamento_bp.route('/vagas/nova', methods=['POST'])
@login_required
def nova_vaga():
    titulo = request.form.get('titulo')
    descricao = request.form.get('descricao')
    local = request.form.get('local')
    salario = request.form.get('salario')
    
    nova_vaga = Vaga(
        titulo=titulo,
        descricao=descricao,
        local=local,
        salario=salario,
        empresa_id=current_user.empresa_id
    )
    db.session.add(nova_vaga)
    db.session.commit() 
    
    fases_padrao = ["Novos Currículos", "Triagem", "Entrevista", "Aprovados"]
    for i, nome_fase in enumerate(fases_padrao):
        fase = FaseRecrutamento(vaga_id=nova_vaga.id, nome=nome_fase, ordem=i, empresa_id=current_user.empresa_id)
        db.session.add(fase)
        
    db.session.commit()
    flash('Nova vaga criada com sucesso! O funil de seleção já está pronto.', 'success')
    return redirect(url_for('recrutamento.dashboard_vagas'))

@recrutamento_bp.route('/vagas/<int:id>/editar', methods=['POST'])
@login_required
def editar_vaga(id):
    """Atualiza as informações e o status de uma vaga existente."""
    vaga = Vaga.query.filter_by(id=id, empresa_id=current_user.empresa_id).first_or_404()
    
    vaga.titulo = request.form.get('titulo')
    vaga.descricao = request.form.get('descricao')
    vaga.local = request.form.get('local')
    vaga.salario = request.form.get('salario')
    vaga.status = request.form.get('status')
    
    db.session.commit()
    flash(f'Vaga "{vaga.titulo}" atualizada com sucesso!', 'success')
    return redirect(url_for('recrutamento.dashboard_vagas'))

@recrutamento_bp.route('/vagas/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_vaga(id):
    """Exclui uma vaga e todo o seu funil de candidaturas associado."""
    vaga = Vaga.query.filter_by(id=id, empresa_id=current_user.empresa_id).first_or_404()
    titulo = vaga.titulo
    
    db.session.delete(vaga)
    db.session.commit()
    
    flash(f'A vaga "{titulo}" e o seu funil foram excluídos.', 'success')
    return redirect(url_for('recrutamento.dashboard_vagas'))

# ==============================================================================
# 🗄️ VORTICE RECRUTAMENTO - BANCO DE TALENTOS E CURRÍCULOS
# ==============================================================================

@recrutamento_bp.route('/banco-talentos', methods=['GET'])
@login_required
def banco_talentos():
    candidatos = Candidato.query.filter_by(empresa_id=current_user.empresa_id).order_by(Candidato.id.desc()).all()
    tags_empresa = TagCandidato.query.filter_by(empresa_id=current_user.empresa_id).all()
    return render_template('recrutamento/banco_talentos.html', candidatos=candidatos, tags_empresa=tags_empresa)

@recrutamento_bp.route('/banco-talentos/novo', methods=['POST'])
@login_required
def novo_candidato():
    nome_manual = request.form.get('nome')
    email_manual = request.form.get('email')
    telefone_manual = request.form.get('telefone')
    tags_manuais = request.form.get('palavras_chave')
    
    arquivo_cv = request.files.get('arquivo_cv')
    url_cv = None
    texto_extraido = None
    
    nome_final = nome_manual
    email_final = email_manual
    telefone_final = telefone_manual
    tags_finais = tags_manuais
    
    if arquivo_cv and arquivo_cv.filename:
        dados_ia = analisar_curriculo_ia(arquivo_cv)
        
        if dados_ia:
            nome_final = nome_manual if nome_manual else dados_ia.get('nome', 'Candidato Sem Nome')
            email_final = email_manual if email_manual else dados_ia.get('email')
            telefone_final = telefone_manual if telefone_manual else dados_ia.get('telefone')
            tags_finais = tags_manuais if tags_manuais else dados_ia.get('palavras_chave')
            texto_extraido = json.dumps(dados_ia) 
        else:
            if not nome_final: nome_final = "Candidato (A Revisar)"
            
        arquivo_cv.seek(0)
            
        bucket_name = os.environ.get('VORTICE_BUCKET')
        if bucket_name:
            try:
                filename = secure_filename(arquivo_cv.filename)
                extensao = filename.rsplit('.', 1)[1].lower() if '.' in filename else 'pdf'
                nome_hash = uuid.uuid4().hex
                
                caminho_gcp = f"cvs/{current_user.empresa_id}/{nome_hash}.{extensao}"
                
                storage_client = storage.Client()
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(caminho_gcp)
                blob.upload_from_file(arquivo_cv, content_type=arquivo_cv.content_type)
                
                url_cv = blob.public_url
            except Exception as e:
                flash(f'Falha no upload para nuvem: {str(e)}', 'error')
                return redirect(url_for('recrutamento.banco_talentos'))
        else:
            flash('Aviso: VORTICE_BUCKET não configurado. CV não foi salvo na nuvem.', 'error')

    if not nome_final and not arquivo_cv:
        flash('É necessário anexar um currículo ou informar o nome.', 'error')
        return redirect(url_for('recrutamento.banco_talentos'))

    novo_cand = Candidato(
        nome=nome_final, email=email_final, telefone=telefone_final,
        palavras_chave=tags_finais, url_curriculo=url_cv,
        texto_extraido=texto_extraido, empresa_id=current_user.empresa_id
    )
    
    db.session.add(novo_cand)
    db.session.commit()
    flash(f'Sucesso! O CV de {nome_final} foi processado.', 'success')
    return redirect(url_for('recrutamento.banco_talentos'))

@recrutamento_bp.route('/banco-talentos/<int:id>/cv', methods=['GET'])
@login_required
def ver_cv(id):
    """Busca o PDF privadamente no GCS e envia para o navegador de forma segura."""
    candidato = Candidato.query.filter_by(id=id, empresa_id=current_user.empresa_id).first_or_404()
    
    if not candidato.url_curriculo:
        flash('Este candidato não possui currículo anexado.', 'error')
        return redirect(url_for('recrutamento.banco_talentos'))
        
    try:
        blob_name = candidato.url_curriculo
        if 'storage.googleapis.com' in blob_name:
            blob_name = blob_name.split('/', 4)[-1]
            
        bucket_name = os.environ.get('VORTICE_BUCKET')
        storage_client = storage.Client()
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(blob_name)
        
        file_bytes = blob.download_as_bytes()
        
        return send_file(
            io.BytesIO(file_bytes),
            mimetype='application/pdf',
            as_attachment=False,
            download_name=f"CV_{candidato.nome}.pdf"
        )
    except Exception as e:
        flash(f'Erro ao abrir documento privadamente: {str(e)}', 'error')
        return redirect(url_for('recrutamento.banco_talentos'))

@recrutamento_bp.route('/banco-talentos/<int:id>/excluir', methods=['POST'])
@login_required
def excluir_candidato(id):
    """Exclui o candidato e o PDF do Google Cloud Storage."""
    candidato = Candidato.query.filter_by(id=id, empresa_id=current_user.empresa_id).first_or_404()
    
    if candidato.url_curriculo:
        try:
            blob_name = candidato.url_curriculo
            if 'storage.googleapis.com' in blob_name:
                blob_name = blob_name.split('/', 4)[-1]
            
            bucket_name = os.environ.get('VORTICE_BUCKET')
            if bucket_name:
                storage_client = storage.Client()
                bucket = storage_client.bucket(bucket_name)
                blob = bucket.blob(blob_name)
                if blob.exists():
                    blob.delete()
        except Exception:
            pass
            
    nome = candidato.nome
    db.session.delete(candidato)
    db.session.commit()
    
    flash(f'Candidato {nome} e o seu currículo foram excluídos.', 'success')
    return redirect(url_for('recrutamento.banco_talentos'))

# ==============================================================================
# 🏷️ VORTICE RECRUTAMENTO - SISTEMA DE TAGS COLORIDAS
# ==============================================================================

@recrutamento_bp.route('/tags/nova', methods=['POST'])
@login_required
def nova_tag():
    """Cria uma nova tag colorida para a empresa."""
    nome = request.form.get('nome')
    cor = request.form.get('cor', 'blue')
    
    nova = TagCandidato(nome=nome, cor=cor, empresa_id=current_user.empresa_id)
    db.session.add(nova)
    db.session.commit()
    flash(f'Tag "{nome}" criada com sucesso!', 'success')
    return redirect(url_for('recrutamento.banco_talentos'))

@recrutamento_bp.route('/banco-talentos/<int:candidato_id>/add-tag', methods=['POST'])
@login_required
def adicionar_tag_candidato(candidato_id):
    """Atribui uma tag colorida a um candidato."""
    candidato = Candidato.query.filter_by(id=candidato_id, empresa_id=current_user.empresa_id).first_or_404()
    tag_id = request.form.get('tag_id')
    
    if tag_id:
        tag = TagCandidato.query.filter_by(id=tag_id, empresa_id=current_user.empresa_id).first()
        if tag and tag not in candidato.tags_coloridas:
            candidato.tags_coloridas.append(tag)
            db.session.commit()
            flash('Tag atribuída com sucesso!', 'success')
            
    return redirect(url_for('recrutamento.banco_talentos'))

@recrutamento_bp.route('/banco-talentos/<int:candidato_id>/remove-tag/<int:tag_id>', methods=['POST'])
@login_required
def remover_tag_candidato(candidato_id, tag_id):
    """Remove uma tag de um candidato."""
    candidato = Candidato.query.filter_by(id=candidato_id, empresa_id=current_user.empresa_id).first_or_404()
    tag = TagCandidato.query.filter_by(id=tag_id, empresa_id=current_user.empresa_id).first_or_404()
    
    if tag in candidato.tags_coloridas:
        candidato.tags_coloridas.remove(tag)
        db.session.commit()
        
    return redirect(url_for('recrutamento.banco_talentos'))

# ==============================================================================
# 🎯 VORTICE RECRUTAMENTO - KANBAN (DRAG & DROP)
# ==============================================================================

@recrutamento_bp.route('/vagas/<int:vaga_id>/kanban', methods=['GET'])
@login_required
def kanban_vaga(vaga_id):
    vaga = Vaga.query.filter_by(id=vaga_id, empresa_id=current_user.empresa_id).first_or_404()
    fases = FaseRecrutamento.query.filter_by(vaga_id=vaga.id).order_by(FaseRecrutamento.ordem).all()
    
    subquery = db.session.query(Candidatura.candidato_id).filter(Candidatura.vaga_id == vaga_id)
    candidatos_disponiveis = Candidato.query.filter(
        Candidato.empresa_id == current_user.empresa_id, 
        ~Candidato.id.in_(subquery)
    ).all()
    
    tags_empresa = TagCandidato.query.filter_by(empresa_id=current_user.empresa_id).all()
    
    return render_template('recrutamento/kanban.html', vaga=vaga, fases=fases, candidatos=candidatos_disponiveis, tags_empresa=tags_empresa)

@recrutamento_bp.route('/vagas/<int:vaga_id>/vincular-candidato', methods=['POST'])
@login_required
def vincular_candidato(vaga_id):
    vaga = Vaga.query.filter_by(id=vaga_id, empresa_id=current_user.empresa_id).first_or_404()
    candidato_id = request.form.get('candidato_id')
    primeira_fase = FaseRecrutamento.query.filter_by(vaga_id=vaga.id).order_by(FaseRecrutamento.ordem).first()
    
    if candidato_id and primeira_fase:
        nova_cand = Candidatura(candidato_id=candidato_id, vaga_id=vaga.id, fase_id=primeira_fase.id)
        db.session.add(nova_cand)
        db.session.commit()
        flash('Candidato inserido no funil com sucesso!', 'success')
        
    return redirect(url_for('recrutamento.kanban_vaga', vaga_id=vaga.id))

@recrutamento_bp.route('/api/kanban/mover', methods=['POST'])
@login_required
def mover_candidato():
    data = request.get_json()
    candidatura_id = data.get('candidatura_id')
    nova_fase_id = data.get('nova_fase_id')
    
    candidatura = Candidatura.query.join(Vaga).filter(
        Candidatura.id == candidatura_id, 
        Vaga.empresa_id == current_user.empresa_id
    ).first()
    
    if candidatura:
        candidatura.fase_id = nova_fase_id
        db.session.commit()
        return jsonify({'success': True})
        
    return jsonify({'success': False, 'error': 'Não encontrado'}), 404

@recrutamento_bp.route('/vagas/remover-candidatura/<int:candidatura_id>', methods=['POST'])
@login_required
def remover_do_funil(candidatura_id):
    """Remove o candidato da vaga (mas mantém no banco de talentos)."""
    candidatura = Candidatura.query.join(Vaga).filter(
        Candidatura.id == candidatura_id, 
        Vaga.empresa_id == current_user.empresa_id
    ).first_or_404()
    
    vaga_id = candidatura.vaga_id
    db.session.delete(candidatura)
    db.session.commit()
    
    flash('Candidato removido do funil desta vaga.', 'success')
    return redirect(url_for('recrutamento.kanban_vaga', vaga_id=vaga_id))

