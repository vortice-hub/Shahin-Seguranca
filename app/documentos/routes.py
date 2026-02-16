from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, jsonify
from flask_login import login_required, current_user
from app.extensions import db
from app.models import User, Holerite, Recibo
from app.utils import get_brasil_time, remove_accents, master_required
from app.documentos.utils import gerar_pdf_recibo
import io
from pypdf import PdfReader, PdfWriter
from datetime import datetime

documentos_bp = Blueprint('documentos', __name__, template_folder='templates', url_prefix='/documentos')

# --- ROTAS DO MASTER (ADMINISTRAÇÃO) ---

@documentos_bp.route('/admin')
@login_required
@master_required
def dashboard_documentos():
    # Busca os últimos 50 recibos para monitoramento de visualização
    ultimos_recibos = Recibo.query.order_by(Recibo.created_at.desc()).limit(50).all()
    
    # Busca os últimos uploads de holerites (agrupados ou lista simples)
    ultimos_holerites = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    
    return render_template('documentos/dashboard.html', recibos=ultimos_recibos, holerites=ultimos_holerites)

@documentos_bp.route('/admin/holerites', methods=['GET', 'POST'])
@login_required
@master_required
def admin_holerites():
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            Holerite.query.delete()
            db.session.commit()
            flash('Histórico de holerites removido.', 'warning')
            return redirect(url_for('documentos.admin_holerites'))

        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        if not file or not mes_ref: return redirect(url_for('documentos.admin_holerites'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            
            def encontrar_user(texto):
                texto_limpo = remove_accents(texto).upper()
                for u in User.query.all():
                    # Ignora usuário terminal na busca do PDF também
                    if u.username == 'terminal': continue
                    
                    nome_limpo = remove_accents(u.real_name).upper().strip()
                    if len(nome_limpo.split()) > 1 and nome_limpo in texto_limpo:
                        return u
                return None

            for page in reader.pages:
                user = encontrar_user(page.extract_text())
                if user:
                    writer = PdfWriter(); writer.add_page(page)
                    out = io.BytesIO(); writer.write(out)
                    
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.conteudo_pdf = out.getvalue()
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, conteudo_pdf=out.getvalue())
                        db.session.add(novo)
                    sucesso += 1
            db.session.commit()
            flash(f'Sucesso: {sucesso} holerites processados.', 'success')
        except Exception as e:
            db.session.rollback(); flash(f'Erro: {e}', 'error')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('documentos/admin_upload_holerite.html', uploads=ultimos)

@documentos_bp.route('/admin/recibo/novo', methods=['GET', 'POST'])
@login_required
@master_required
def admin_novo_recibo():
    # FILTRO: Remove o usuário 'terminal' e ordena por nome
    users = User.query.filter(User.username != 'terminal').order_by(User.real_name).all()
    
    if request.method == 'POST':
        try:
            user_id = request.form.get('user_id')
            user = User.query.get(user_id)
            if not user: raise Exception("Funcionário inválido")
            
            valor = float(request.form.get('valor'))
            data_pagto = datetime.strptime(request.form.get('data_pagamento'), '%Y-%m-%d').date()
            
            recibo = Recibo(
                user_id=user.id,
                valor=valor,
                data_pagamento=data_pagto,
                tipo_vale_alimentacao = 'va' in request.form,
                tipo_vale_transporte = 'vt' in request.form,
                tipo_assiduidade = 'assiduidade' in request.form,
                tipo_cesta_basica = 'cesta' in request.form,
                forma_pagamento = request.form.get('forma_pagamento')
            )
            
            pdf_bytes = gerar_pdf_recibo(recibo, user)
            recibo.conteudo_pdf = pdf_bytes
            
            db.session.add(recibo)
            db.session.commit()
            
            flash(f'Recibo gerado para {user.real_name}!', 'success')
            return redirect(url_for('documentos.dashboard_documentos'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao gerar recibo: {e}', 'error')
            
    return render_template('documentos/novo_recibo.html', users=users, hoje=get_brasil_time().strftime('%Y-%m-%d'))

# --- ROTAS DO USUÁRIO ---

@documentos_bp.route('/meus-documentos')
@login_required
def meus_documentos():
    holerites = Holerite.query.filter_by(user_id=current_user.id).all()
    lista_docs = []
    
    for h in holerites:
        lista_docs.append({
            'tipo': 'Holerite',
            'titulo': f'Folha: {h.mes_referencia}',
            'data': h.enviado_em,
            'id': h.id,
            'rota_download': 'baixar_holerite',
            'visualizado': h.visualizado,
            'icone': 'fa-file-invoice-dollar',
            'cor': 'blue'
        })
        
    recibos = Recibo.query.filter_by(user_id=current_user.id).all()
    for r in recibos:
        lista_docs.append({
            'tipo': 'Recibo',
            'titulo': f'Recibo: R$ {r.valor:.2f}',
            'data': r.created_at,
            'id': r.id,
            'rota_download': 'baixar_recibo',
            'visualizado': r.visualizado,
            'icone': 'fa-file-signature',
            'cor': 'emerald'
        })
        
    lista_docs.sort(key=lambda x: x['data'], reverse=True)
    
    return render_template('documentos/meus_documentos.html', docs=lista_docs)

# --- DOWNLOADS E API ---

@documentos_bp.route('/baixar/holerite/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if current_user.role != 'Master' and doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    
    if not doc.visualizado and current_user.id == doc.user_id:
        doc.visualizado = True; doc.visualizado_em = get_brasil_time(); db.session.commit()
        
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Holerite_{doc.mes_referencia}.pdf")

@documentos_bp.route('/baixar/recibo/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_recibo(id):
    doc = Recibo.query.get_or_404(id)
    if current_user.role != 'Master' and doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    
    if not doc.visualizado and current_user.id == doc.user_id:
        doc.visualizado = True; db.session.commit()
        
    return send_file(io.BytesIO(doc.conteudo_pdf), mimetype='application/pdf', as_attachment=True, download_name=f"Recibo_Pagamento_{doc.id}.pdf")

@documentos_bp.route('/api/user-info/<int:user_id>')
@login_required
@master_required
def api_user_info(user_id):
    u = User.query.get_or_404(user_id)
    return jsonify({
        'real_name': u.real_name,
        'cpf': u.cpf,
        'razao_social': u.razao_social_empregadora,
        'cnpj': u.cnpj_empregador
    })



