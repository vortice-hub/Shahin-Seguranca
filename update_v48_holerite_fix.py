import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V48: Fix Holerite 401 (Raw Resource) e Tabela de Auditoria para Master"

# --- 1. APP/ROUTES/HOLERITES.PY (Upload corrigido e Auditoria) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import cloudinary
import cloudinary.uploader
import re
import io
from pypdf import PdfReader, PdfWriter
from sqlalchemy import desc

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

# Configuração de Fallback (Garante que funcione mesmo sem ENV)
try:
    if not cloudinary.config().cloud_name:
        cloudinary.config(
            cloud_name = "dxb4fbdjy",
            api_key = "537342766187832",
            api_secret = "cbINpCjQtRh7oKp-uVX2YPdOKaI"
        )
except: pass

def encontrar_usuario_por_nome(texto_pagina):
    texto_limpo = remove_accents(texto_pagina).upper()
    users = User.query.all()
    candidatos = []
    for user in users:
        nome_user_limpo = remove_accents(user.real_name).upper().strip()
        # Verifica se o nome tem pelo menos 2 partes para evitar falsos positivos com nomes curtos
        if len(nome_user_limpo.split()) > 1 and nome_user_limpo in texto_limpo:
            candidatos.append(user)
    if len(candidatos) == 1: return candidatos[0]
    return None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        
        if not file or not mes_ref:
            flash('Selecione arquivo e mês.')
            return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            falha = 0
            
            for i, page in enumerate(reader.pages):
                texto = page.extract_text()
                user = encontrar_usuario_por_nome(texto)
                
                if user:
                    writer = PdfWriter()
                    writer.add_page(page)
                    output_stream = io.BytesIO()
                    writer.write(output_stream)
                    output_stream.seek(0)
                    
                    # Nome do arquivo único
                    # Adiciona .pdf no final para garantir extensao no raw
                    filename = f"holerite_{user.id}_{mes_ref}_{int(get_brasil_time().timestamp())}.pdf"
                    
                    # Upload CORRIGIDO (Raw para evitar processamento de imagem e erro 401)
                    upload = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="raw", # Mudança chave: RAW trata como arquivo genérico
                        folder="holerites_shahin",
                        access_mode="public"
                    )
                    
                    url = upload.get('secure_url')
                    pid = upload.get('public_id')
                    
                    # Salva no Banco
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.url_arquivo = url
                        existente.public_id = pid
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, url_arquivo=url, public_id=pid)
                        db.session.add(novo)
                    
                    sucesso += 1
                else:
                    falha += 1
            
            db.session.commit()
            flash(f'Importação Finalizada: {sucesso} enviados. {falha} páginas não identificadas.')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro crítico: {str(e)}')

    # Busca histórico de uploads recentes para mostrar ao Master (Feedback Visual)
    ultimos_uploads = Holerite.query.join(User).order_by(Holerite.enviado_em.desc()).limit(50).all()
            
    return render_template('admin_upload_holerite.html', uploads=ultimos_uploads)

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

@holerite_bp.route('/confirmar-recebimento/<int:id>', methods=['POST'])
@login_required
def confirmar_recebimento(id):
    doc = Holerite.query.get_or_404(id)
    if doc.user_id != current_user.id: return redirect(url_for('main.dashboard'))
    
    if not doc.visualizado:
        doc.visualizado = True
        doc.visualizado_em = get_brasil_time()
        db.session.commit()
        flash('Confirmado.')
        
    return redirect(doc.url_arquivo)
"""

# --- 2. TEMPLATE ADMIN UPLOAD (Com Tabela de Auditoria) ---
FILE_TPL_ADMIN = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-4xl mx-auto">
    <div class="mb-6">
        <h2 class="text-2xl font-bold text-slate-800">Importação de Holerites</h2>
        <p class="text-sm text-slate-500">Envie o PDF da folha. O sistema corta e distribui.</p>
    </div>

    <!-- Área de Upload -->
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-8 mb-8">
        <form action="/holerites/admin/importar" method="POST" enctype="multipart/form-data" class="space-y-6">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-6">
                <div>
                    <label class="label-pro">Mês de Referência</label>
                    <input type="month" name="mes_ref" class="input-pro" required>
                </div>
                <div>
                    <label class="label-pro">Arquivo PDF</label>
                    <input type="file" name="arquivo_pdf" accept=".pdf" class="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" required>
                </div>
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-md transition flex items-center justify-center gap-2" onclick="this.innerHTML='<i class=\\'fas fa-spinner fa-spin\\'></i> Processando (Pode demorar)...';">
                <i class="fas fa-cloud-upload-alt"></i> PROCESSAR E DISTRIBUIR
            </button>
        </form>
    </div>

    <!-- Tabela de Auditoria (Visualização do Master) -->
    <h3 class="text-lg font-bold text-slate-700 mb-4 px-2">Últimos Envios (Auditoria)</h3>
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div class="overflow-x-auto">
            <table class="w-full text-left text-sm text-slate-600">
                <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold border-b border-slate-100">
                    <tr>
                        <th class="px-6 py-3">Funcionário</th>
                        <th class="px-6 py-3">Referência</th>
                        <th class="px-6 py-3">Enviado Em</th>
                        <th class="px-6 py-3 text-center">Status Leitura</th>
                        <th class="px-6 py-3 text-right">Ação</th>
                    </tr>
                </thead>
                <tbody class="divide-y divide-slate-100">
                    {% for item in uploads %}
                    <tr class="hover:bg-slate-50 transition">
                        <td class="px-6 py-3 font-bold text-slate-800">{{ item.user.real_name }}</td>
                        <td class="px-6 py-3">{{ item.mes_referencia }}</td>
                        <td class="px-6 py-3 text-xs">{{ item.enviado_em.strftime('%d/%m %H:%M') }}</td>
                        <td class="px-6 py-3 text-center">
                            {% if item.visualizado %}
                                <span class="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-[10px] font-bold uppercase">Lido</span>
                            {% else %}
                                <span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-[10px] font-bold uppercase">Pendente</span>
                            {% endif %}
                        </td>
                        <td class="px-6 py-3 text-right">
                            <a href="{{ item.url_arquivo }}" target="_blank" class="text-blue-600 hover:underline text-xs font-bold"><i class="fas fa-eye"></i> Ver</a>
                        </td>
                    </tr>
                    {% else %}
                    <tr>
                        <td colspan="5" class="px-6 py-8 text-center text-slate-400">Nenhum envio registrado recentemente.</td>
                    </tr>
                    {% endfor %}
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
        print("\n>>> SUCESSO V48! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V48 HOLERITES: {PROJECT_NAME} ---")
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    write_file("app/templates/admin_upload_holerite.html", FILE_TPL_ADMIN)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


