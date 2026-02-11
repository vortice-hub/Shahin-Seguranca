import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V53: Fix Holerite - Implementacao de Proxy de Download (Bypass Cloudinary Link)"

# --- 1. REQUIREMENTS (Adicionando 'requests' para baixar o arquivo) ---
FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
flask-login
werkzeug
cloudinary
pypdf
requests
"""

# --- 2. APP/ROUTES/HOLERITES.PY (Logica de Proxy) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, make_response
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import cloudinary
import cloudinary.uploader
import io
import logging
import requests
from pypdf import PdfReader, PdfWriter

logger = logging.getLogger(__name__)

holerite_bp = Blueprint('holerite', __name__, url_prefix='/holerites')

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
        if len(nome_user_limpo.split()) > 1 and nome_user_limpo in texto_limpo:
            candidatos.append(user)
    if len(candidatos) == 1: return candidatos[0]
    return None

@holerite_bp.route('/admin/importar', methods=['GET', 'POST'])
@login_required
def admin_importar():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        if request.form.get('acao') == 'limpar_tudo':
            try:
                Holerite.query.delete()
                db.session.commit()
                flash('Limpeza concluída.')
            except Exception as e:
                db.session.rollback()
                flash(f'Erro: {e}')
            return redirect(url_for('holerite.admin_importar'))

        file = request.files.get('arquivo_pdf')
        mes_ref = request.form.get('mes_ref')
        
        if not file: return redirect(url_for('holerite.admin_importar'))
            
        try:
            reader = PdfReader(file)
            sucesso = 0
            
            for i, page in enumerate(reader.pages):
                texto = page.extract_text()
                user = encontrar_usuario_por_nome(texto)
                
                if user:
                    writer = PdfWriter()
                    writer.add_page(page)
                    output_stream = io.BytesIO()
                    writer.write(output_stream)
                    output_stream.seek(0)
                    
                    filename = f"holerite_{user.id}_{mes_ref}_{int(get_brasil_time().timestamp())}"
                    
                    # Upload como AUTO (Deixa o Cloudinary decidir o melhor jeito)
                    upload_result = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="auto", 
                        folder="holerites_v53"
                    )
                    
                    url_pdf = upload_result.get('secure_url')
                    pid = upload_result.get('public_id')
                    
                    existente = Holerite.query.filter_by(user_id=user.id, mes_referencia=mes_ref).first()
                    if existente:
                        existente.url_arquivo = url_pdf
                        existente.public_id = pid
                        existente.enviado_em = get_brasil_time()
                        existente.visualizado = False
                    else:
                        novo = Holerite(user_id=user.id, mes_referencia=mes_ref, url_arquivo=url_pdf, public_id=pid)
                        db.session.add(novo)
                    
                    sucesso += 1
            
            db.session.commit()
            flash(f'Sucesso: {sucesso} holerites enviados.')
            
        except Exception as e:
            logger.error(f"ERRO UPLOAD: {e}")
            db.session.rollback()
            flash(f'Erro: {str(e)}')

    ultimos = Holerite.query.order_by(Holerite.enviado_em.desc()).limit(20).all()
    return render_template('admin_upload_holerite.html', uploads=ultimos)

@holerite_bp.route('/meus-documentos')
@login_required
def meus_holerites():
    docs = Holerite.query.filter_by(user_id=current_user.id).order_by(Holerite.mes_referencia.desc()).all()
    return render_template('meus_holerites.html', holerites=docs)

# --- ROTA DE DOWNLOAD (PROXY) ---
@holerite_bp.route('/baixar/<int:id>', methods=['GET', 'POST'])
@login_required
def baixar_holerite(id):
    doc = Holerite.query.get_or_404(id)
    if doc.user_id != current_user.id: 
        flash("Acesso negado.")
        return redirect(url_for('main.dashboard'))
    
    # Registra visualização
    if not doc.visualizado:
        doc.visualizado = True
        doc.visualizado_em = get_brasil_time()
        db.session.commit()
        
    try:
        # O PULO DO GATO: O servidor baixa o arquivo do Cloudinary
        response = requests.get(doc.url_arquivo)
        
        if response.status_code == 200:
            # Cria um arquivo na memória para entregar ao usuário
            arquivo_memoria = io.BytesIO(response.content)
            
            # Define o nome do arquivo para download
            nome_download = f"Holerite_{doc.mes_referencia}.pdf"
            
            return send_file(
                arquivo_memoria,
                mimetype='application/pdf',
                as_attachment=True, # Força o download
                download_name=nome_download
            )
        else:
            flash(f"Erro ao buscar arquivo na nuvem (Status {response.status_code}). Tente novamente.")
            return redirect(url_for('holerite.meus_holerites'))
            
    except Exception as e:
        logger.error(f"Erro Proxy Download: {e}")
        flash("Erro ao baixar documento. Contate o RH.")
        return redirect(url_for('holerite.meus_holerites'))
"""

# --- 3. TEMPLATE MEUS HOLERITES (Aponta para nova rota) ---
FILE_TPL_MEUS = """
{% extends 'base.html' %}
{% block content %}
<div class="mb-6"><h2 class="text-2xl font-bold text-slate-800">Meus Holerites</h2></div>
<div class="grid gap-4">
    {% for h in holerites %}
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 flex justify-between items-center">
        <div class="flex items-center gap-4">
            <div class="w-12 h-12 rounded-lg flex items-center justify-center text-2xl {% if h.visualizado %} bg-emerald-100 text-emerald-600 {% else %} bg-blue-100 text-blue-600 {% endif %}"><i class="fas fa-file-invoice-dollar"></i></div>
            <div>
                <div class="font-bold text-slate-800 text-lg">{{ h.mes_referencia }}</div>
                <div class="text-xs text-slate-500">{% if h.visualizado %}<span class="text-emerald-600 font-bold"><i class="fas fa-check"></i> Recebido: {{ h.visualizado_em.strftime('%d/%m/%Y %H:%M') }}</span>{% else %}<span class="text-blue-600 font-bold">Pendente de Assinatura</span>{% endif %}</div>
            </div>
        </div>
        <!-- Form aponta para a rota de download direta -->
        <form action="/holerites/baixar/{{ h.id }}" method="POST">
            <button type="submit" class="px-4 py-2 rounded-lg font-bold text-sm transition shadow-sm border {% if h.visualizado %} bg-white text-slate-600 border-slate-200 hover:bg-slate-50 {% else %} bg-blue-600 text-white border-blue-600 hover:bg-blue-700 animate-pulse {% endif %}">
                {% if h.visualizado %} <i class="fas fa-download mr-1"></i> Baixar PDF {% else %} <i class="fas fa-pen-nib mr-1"></i> Confirmar e Baixar {% endif %}
            </button>
        </form>
    </div>
    {% else %}
    <div class="text-center py-12 text-slate-400"><i class="fas fa-folder-open text-4xl mb-4 opacity-50"></i><p>Nenhum documento disponível.</p></div>
    {% endfor %}
</div>
{% endblock %}
"""

# --- 4. TEMPLATE ADMIN (Atualiza para usar link direto visualizacao) ---
FILE_TPL_ADMIN = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-4xl mx-auto">
    <div class="mb-6 flex justify-between items-center">
        <div><h2 class="text-2xl font-bold text-slate-800">Importação de Holerites</h2><p class="text-sm text-slate-500">Envie o PDF da folha.</p></div>
        <form action="/holerites/admin/importar" method="POST" onsubmit="return confirm('Apagar tudo?')"><input type="hidden" name="acao" value="limpar_tudo"><button type="submit" class="text-xs text-red-500 hover:text-red-700 underline font-bold">Limpar Histórico</button></form>
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
        <table class="w-full text-left text-sm text-slate-600">
            <thead class="bg-slate-50 text-xs uppercase text-slate-400 font-bold border-b border-slate-100"><tr><th class="px-6 py-3">Funcionário</th><th class="px-6 py-3">Referência</th><th class="px-6 py-3">Enviado Em</th><th class="px-6 py-3 text-center">Status</th><th class="px-6 py-3 text-right">Ação</th></tr></thead>
            <tbody class="divide-y divide-slate-100">
                {% for item in uploads %}
                <tr class="hover:bg-slate-50 transition">
                    <td class="px-6 py-3 font-bold text-slate-800">{{ item.user.real_name }}</td>
                    <td class="px-6 py-3">{{ item.mes_referencia }}</td>
                    <td class="px-6 py-3 text-xs">{{ item.enviado_em.strftime('%d/%m %H:%M') }}</td>
                    <td class="px-6 py-3 text-center">{% if item.visualizado %}<span class="bg-emerald-100 text-emerald-700 px-2 py-1 rounded text-[10px] font-bold uppercase">Lido</span>{% else %}<span class="bg-yellow-100 text-yellow-700 px-2 py-1 rounded text-[10px] font-bold uppercase">Pendente</span>{% endif %}</td>
                    <!-- O Master pode baixar usando a mesma rota de proxy -->
                    <td class="px-6 py-3 text-right">
                        <form action="/holerites/baixar/{{ item.id }}" method="POST" target="_blank" style="display:inline;">
                            <button type="submit" class="text-blue-600 hover:underline text-xs font-bold"><i class="fas fa-eye"></i> Ver</button>
                        </form>
                    </td>
                </tr>
                {% else %}<tr><td colspan="5" class="px-6 py-8 text-center text-slate-400">Nenhum envio recente.</td></tr>{% endfor %}
            </tbody>
        </table>
    </div>
</div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; } .input-pro { width: 100%; background-color: #f8fafc; border: 1px solid #e2e8f0; border-radius: 0.5rem; padding: 0.75rem 1rem; outline: none; }</style>
{% endblock %}
"""

# --- FUNÇÕES ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Atualizado: {path}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V53! PROXY DE DOWNLOAD ATIVADO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V53 PROXY: {PROJECT_NAME} ---")
    write_file("requirements.txt", FILE_REQ)
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    write_file("app/templates/meus_holerites.html", FILE_TPL_MEUS)
    write_file("app/templates/admin_upload_holerite.html", FILE_TPL_ADMIN)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


