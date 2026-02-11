from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import io
import logging
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)
holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

def encontrar_usuario_por_nome(texto_pagina):
    texto_limpo = remove_accents(texto_pagina).upper()
    users = User.query.all()
    candidatos = []
    for u in users:
        nome_limpo = remove_accents(u.real_name).upper().strip()
        if len(nome_limpo.split()) > 1 and nome_limpo in texto_limpo:
            candidatos.append(u)
    return candidatos[0] if len(candidatos) == 1 else None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            Holerite.query.delete(); db.session.commit()
            flash('Histórico limpo.'); return redirect(url_for('holerite.admin_importar'))

        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        if not file or not mes_ref: return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            for page in reader.pages:
                user = encontrar_usuario_por_nome(page.extract_text())
                if user:
                    writer = PdfWriter(); writer.add_page(page)
                    out = io.BytesIO(); writer.write(out); binary_data = out.getvalue()
                    
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.conteudo_pdf = binary_data
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, conteudo_pdf=binary_data)
                        db.session.add(novo)
                    sucesso += 1
            db.session.commit()
            flash(f'Sucesso: {sucesso} holerites guardados no sistema.')
        except Exception as e:
            db.session.rollback(); flash(f'Erro: {e}')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('admin_upload_holerite.html', uploads=ultimos)

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

@holerite_bp.route('/baixar/<int:id>', methods=['POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    
    if not doc.visualizado:
        doc.visualizado = True; doc.visualizado_em = get_brasil_time(); db.session.commit()
        
    if not doc.conteudo_pdf:
        flash("Arquivo não encontrado no banco."); return redirect(url_for('holerite.meus_holerites'))
        
    return send_file(
        io.BytesIO(doc.conteudo_pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Holerite_{doc.mes_referencia}.pdf"
    )