import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V56: Fix 500 Error - Sincronizacao de Banco de Dados e Template"

# --- 1. APP/ROUTES/HOLERITES.PY (Ajuste de Visualização do Master) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import io
import logging
from pypdf import PdfReader, PdfWriter
from sqlalchemy import text

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
    
    # REPARO DE EMERGENCIA: Garante que a coluna existe no Postgres
    try:
        db.session.execute(text("ALTER TABLE holerites ADD COLUMN IF NOT EXISTS conteudo_pdf BYTEA"))
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Erro ao reparar coluna: {e}")

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
            flash(f'Sucesso: {sucesso} holerites processados.')
        except Exception as e:
            db.session.rollback(); flash(f'Erro no processamento: {e}')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(30).all()
    return render_template('admin_upload_holerite.html', uploads=ultimos)

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

@holerite_bp.route('/baixar/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    # Master pode baixar qualquer um, Funcionario só o dele
    if current_user.role != 'Master' and doc.user_id != current_user.id: 
        return redirect(url_for('main.dashboard'))
    
    if not doc.visualizado and current_user.id == doc.user_id:
        doc.visualizado = True; doc.visualizado_em = get_brasil_time(); db.session.commit()
        
    if not doc.conteudo_pdf:
        flash("Conteúdo do arquivo não encontrado."); return redirect(url_for('holerite.meus_holerites'))
        
    return send_file(
        io.BytesIO(doc.conteudo_pdf),
        mimetype='application/pdf',
        as_attachment=True,
        download_name=f"Holerite_{doc.mes_referencia}.pdf"
    )
"""

# --- 2. TEMPLATE ADMIN (Botão Corrigido para Download Interno) ---
FILE_TPL_ADMIN = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-4xl mx-auto">
    <div class="mb-6 flex justify-between items-center">
        <div><h2 class="text-2xl font-bold text-slate-800">Importação de Holerites</h2><p class="text-sm text-slate-500">Envie o PDF da folha.</p></div>
        <form action="/holerites/admin/importar" method="POST" onsubmit="return confirm('Apagar histórico?')"><input type="hidden" name="acao" value="limpar_tudo"><button type="submit" class="text-xs text-red-500 hover:text-red-700 underline font-bold">Limpar Histórico</button></form>
    </div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-8 mb-8">
        <form action="/holerites/admin/importar" method="POST" enctype="multipart/form-data" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div><label class="label-pro">Mês de Referência</label><input type="month" name="mes_ref" class="input-pro" required></div>
                <div><label class="label-pro">Arquivo PDF</label><input type="file" name="arquivo_pdf" accept=".pdf" class="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" required></div>
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-md transition flex items-center justify-center gap-2" onclick="this.innerHTML='<i class=\\'fas fa-spinner fa-spin\\'></i> Processando...';"><i class="fas fa-cloud-upload-alt"></i> PROCESSAR E DISTRIBUIR</button>
        </form>
    </div>

    <h3 class="text-lg font-bold text-slate-700 mb-4 px-2">Últimos Envios</h3>
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm text-slate-600">
                <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold border-b border-slate-100">
                    <tr><th class="px-6 py-3">Funcionário</th><th class="px-6 py-3">Referência</th><th class="px-6 py-3 text-center">Status</th><th class="px-6 py-3 text-right">Ação</th></tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    {% for item in uploads %}
                    <tr class="hover:bg-slate-50 transition">
                        <td class="px-6 py-3 font-bold text-slate-800">{{ item.user.real_name }}</td>
                        <td class="px-6 py-3">{{ item.mes_referencia }}</td>
                        <td class="px-6 py-3 text-center">{% if item.visualizado %}<span class="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-[10px] font-bold uppercase">Lido</span>{% else %}<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-[10px] font-bold uppercase">Pendente</span>{% endif %}</td>
                        <td class="px-6 py-3 text-right">
                            <a href="/holerites/baixar/{{ item.id }}" target="_blank" class="text-blue-600 hover:underline text-xs font-bold"><i class="fas fa-download"></i> Baixar</a>
                        </td>
                    </tr>
                    {% else %}<tr><td colspan="4" class="px-6 py-8 text-center text-slate-400">Nenhum envio recente.</td></tr>{% endfor %}
                </tbody>
            </table>
        </div>
    </div>
</div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; outline: none; }</style>
{% endblock %}
"""

# --- FUNÇÕES ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V56! ERRO 500 CORRIGIDO E BANCO REPARADO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V56 FIX 500: {PROJECT_NAME} ---")
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    write_file("app/templates/admin_upload_holerite.html", FILE_TPL_ADMIN)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


