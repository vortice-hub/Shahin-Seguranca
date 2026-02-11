import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V47: Holerite por Nome e Importacao de Funcionarios via CSV"

# --- 1. APP/ROUTES/HOLERITES.PY (Lógica alterada para Nome) ---
FILE_BP_HOLERITES = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file
from flask_login import login_required, current_user
from app import db
from app.models import User, Holerite
from app.utils import get_brasil_time, remove_accents
import cloudinary
import cloudinary.uploader
import re
import io
from pypdf import PdfReader, PdfWriter

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
    # Normaliza o texto da pagina (Maiusculo, sem acento)
    texto_limpo = remove_accents(texto_pagina).upper()
    
    # Busca usuarios ativos
    users = User.query.all()
    
    candidatos = []
    
    for user in users:
        # Normaliza nome do usuario
        nome_user_limpo = remove_accents(user.real_name).upper().strip()
        
        # Verifica se o nome completo esta contido no texto da pagina
        if nome_user_limpo in texto_limpo:
            candidatos.append(user)
            
    # Se achou exatamente 1, retorna ele. Se achou 0 ou mais de 1 (homonimos), retorna None por seguranca.
    if len(candidatos) == 1:
        return candidatos[0]
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
                    
                    filename = f"holerite_{user.id}_{mes_ref}_{int(get_brasil_time().timestamp())}"
                    
                    upload = cloudinary.uploader.upload(
                        output_stream, 
                        public_id=filename, 
                        resource_type="auto",
                        folder="holerites_shahin"
                    )
                    
                    url = upload.get('secure_url')
                    pid = upload.get('public_id')
                    
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
            flash(f'Processado: {sucesso} identificados por NOME. {falha} páginas não identificadas/ambíguas.')
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erro: {str(e)}')
            
    return render_template('admin_upload_holerite.html')

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
        flash('Recebimento confirmado.')
    return redirect(doc.url_arquivo)
"""

# --- 2. APP/ROUTES/ADMIN.PY (Rota de Importação CSV) ---
FILE_BP_ADMIN = """
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app import db
from app.models import User, PreCadastro, PontoResumo, PontoAjuste, PontoRegistro
from app.utils import calcular_dia, get_brasil_time
import secrets
import csv
import io
from datetime import datetime, time
from sqlalchemy import func

admin_bp = Blueprint('admin', __name__, url_prefix='/admin')

@admin_bp.route('/usuarios/importar-csv', methods=['GET', 'POST'])
@login_required
def importar_csv():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        file = request.files.get('arquivo_csv')
        if not file:
            flash('Selecione um arquivo CSV.')
            return redirect(url_for('admin.importar_csv'))
            
        try:
            stream = io.StringIO(file.stream.read().decode("UTF8"), newline=None)
            csv_reader = csv.DictReader(stream, delimiter=';') # Padrão Excel BR
            
            count = 0
            for row in csv_reader:
                # Espera colunas: Nome;CPF;Cargo;Salario;Entrada;Saida
                cpf_limpo = row.get('CPF', '').replace('.', '').replace('-', '').strip()
                if not cpf_limpo: continue
                
                # Verifica duplicidade
                if PreCadastro.query.filter_by(cpf=cpf_limpo).first() or User.query.filter_by(cpf=cpf_limpo).first():
                    continue
                    
                pre = PreCadastro(
                    cpf=cpf_limpo,
                    nome_previsto=row.get('Nome', 'Funcionario Importado'),
                    cargo=row.get('Cargo', 'Colaborador'),
                    salario=float(row.get('Salario', 0).replace(',', '.') or 0),
                    horario_entrada=row.get('Entrada', '07:12'),
                    horario_saida=row.get('Saida', '17:00'),
                    # Defaults
                    horario_almoco_inicio='12:00',
                    horario_almoco_fim='13:00',
                    escala='5x2'
                )
                db.session.add(pre)
                count += 1
                
            db.session.commit()
            flash(f'Importação concluída! {count} novos CPFs liberados na lista de espera.')
            return redirect(url_for('admin.gerenciar_usuarios'))
            
        except Exception as e:
            flash(f'Erro ao ler CSV: {e}')
            
    return render_template('admin_importar_csv.html')

@admin_bp.route('/usuarios')
@login_required
def gerenciar_usuarios():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    users = User.query.all(); pendentes = PreCadastro.query.all()
    return render_template('admin_usuarios.html', users=users, pendentes=pendentes)

@admin_bp.route('/usuarios/novo', methods=['GET', 'POST'])
@login_required
def novo_usuario():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        try:
            cpf = request.form.get('cpf').replace('.', '').replace('-', '').strip()
            if User.query.filter_by(cpf=cpf).first(): flash('Erro: CPF já existe.'); return redirect(url_for('admin.novo_usuario'))
            dt_escala = None
            if request.form.get('dt_escala'): dt_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
            pre = PreCadastro(cpf=cpf, nome_previsto=request.form.get('real_name'), cargo=request.form.get('role'), salario=float(request.form.get('salario') or 0), horario_entrada=request.form.get('h_ent'), horario_almoco_inicio=request.form.get('h_alm_ini'), horario_almoco_fim=request.form.get('h_alm_fim'), horario_saida=request.form.get('h_sai'), escala=request.form.get('escala'), data_inicio_escala=dt_escala)
            db.session.add(pre); db.session.commit()
            return render_template('sucesso_usuario.html', nome_real=request.form.get('real_name'), cpf=cpf)
        except Exception as e: db.session.rollback(); flash(f"Erro: {e}"); return redirect(url_for('admin.novo_usuario'))
    return render_template('novo_usuario.html')

@admin_bp.route('/liberar-acesso/excluir/<int:id>')
@login_required
def excluir_pre_cadastro(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    pre = PreCadastro.query.get(id)
    if pre: db.session.delete(pre); db.session.commit(); flash('Removido.')
    return redirect(url_for('admin.gerenciar_usuarios'))

@admin_bp.route('/usuarios/editar/<int:id>', methods=['GET', 'POST'])
@login_required
def editar_usuario(id):
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    user = User.query.get_or_404(id)
    if request.method == 'POST':
        try:
            acao = request.form.get('acao')
            if acao == 'excluir':
                if user.username == 'Thaynara': flash('Erro master.')
                else: 
                    PontoRegistro.query.filter_by(user_id=user.id).delete(); PontoResumo.query.filter_by(user_id=user.id).delete(); PontoAjuste.query.filter_by(user_id=user.id).delete(); db.session.delete(user); db.session.commit(); flash('Excluido.')
                return redirect(url_for('admin.gerenciar_usuarios'))
            elif acao == 'resetar_senha': nova = secrets.token_hex(3); user.set_password(nova); user.is_first_access = True; db.session.commit(); flash(f'Senha: {nova}'); return redirect(url_for('admin.editar_usuario', id=id))
            else:
                user.real_name = request.form.get('real_name'); user.username = request.form.get('username')
                if user.username != 'Thaynara': user.role = request.form.get('role')
                user.salario = float(request.form.get('salario') or 0); user.horario_entrada = request.form.get('h_ent'); user.horario_almoco_inicio = request.form.get('h_alm_ini'); user.horario_almoco_fim = request.form.get('h_alm_fim'); user.horario_saida = request.form.get('h_sai'); user.escala = request.form.get('escala')
                if request.form.get('dt_escala'): user.data_inicio_escala = datetime.strptime(request.form.get('dt_escala'), '%Y-%m-%d').date()
                db.session.commit(); flash('Atualizado.')
                return redirect(url_for('admin.gerenciar_usuarios'))
        except Exception as e: db.session.rollback(); flash(f'Erro: {e}'); return redirect(url_for('admin.editar_usuario', id=id))
    return render_template('editar_usuario.html', user=user)

@admin_bp.route('/solicitacoes', methods=['GET', 'POST'])
@login_required
def admin_solicitacoes():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    if request.method == 'POST':
        try:
            solic = PontoAjuste.query.get(request.form.get('solic_id'))
            decisao = request.form.get('decisao')
            if decisao == 'aprovar':
                solic.status = 'Aprovado'
                if solic.tipo_solicitacao == 'Exclusao':
                    if solic.ponto_original_id: db.session.delete(PontoRegistro.query.get(solic.ponto_original_id))
                elif solic.tipo_solicitacao == 'Edicao':
                    p = PontoRegistro.query.get(solic.ponto_original_id)
                    h, m = map(int, solic.novo_horario.split(':'))
                    p.hora_registro = time(h, m); p.tipo = solic.tipo_batida
                elif solic.tipo_solicitacao == 'Inclusao':
                    h, m = map(int, solic.novo_horario.split(':'))
                    db.session.add(PontoRegistro(user_id=solic.user_id, data_registro=solic.data_referencia, hora_registro=time(h, m), tipo=solic.tipo_batida, latitude='Ajuste', longitude='Manual'))
                db.session.commit(); calcular_dia(solic.user_id, solic.data_referencia); flash('Aprovado.')
            elif decisao == 'reprovar':
                solic.status = 'Reprovado'; solic.motivo_reprovacao = request.form.get('motivo_repro'); db.session.commit(); flash('Reprovado.')
        except Exception as e: db.session.rollback(); flash(f'Erro: {e}')
        return redirect(url_for('admin.admin_solicitacoes'))
    pendentes = PontoAjuste.query.filter_by(status='Pendente').order_by(PontoAjuste.created_at).all()
    dados_extras = {}
    for p in pendentes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    return render_template('admin_solicitacoes.html', solicitacoes=pendentes, extras=dados_extras)

@admin_bp.route('/relatorio-folha', methods=['GET', 'POST'])
@login_required
def admin_relatorio_folha():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    mes_ref = request.form.get('mes_ref') or datetime.now().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = datetime.now(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    if request.method == 'POST' and not request.form.get('acao_zerar'): flash(f'Exibindo dados de {mes_ref}')
    users = User.query.order_by(User.real_name).all()
    relatorio = []
    for u in users:
        try:
            resumos = PontoResumo.query.filter(PontoResumo.user_id == u.id, func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).all()
            total_saldo = sum(r.minutos_saldo for r in resumos)
            sinal = "+" if total_saldo >= 0 else "-"
            abs_s = abs(total_saldo)
            sal_val = u.salario if u.salario else 0.0
            relatorio.append({'nome': u.real_name, 'cargo': u.role, 'salario': sal_val, 'saldo_minutos': total_saldo, 'saldo_formatado': f"{sinal}{abs_s // 60:02d}:{abs_s % 60:02d}", 'status': 'Crédito' if total_saldo >= 0 else 'Débito'})
        except: continue
    return render_template('admin_relatorio_folha.html', relatorio=relatorio, mes_ref=mes_ref)

@admin_bp.route('/relatorio-folha/zerar', methods=['POST'])
@login_required
def zerar_relatorio():
    if current_user.role != 'Master': return redirect(url_for('main.dashboard'))
    mes_ref = request.form.get('mes_ref')
    if not mes_ref: return redirect(url_for('admin.admin_relatorio_folha'))
    try:
        ano, mes = map(int, mes_ref.split('-'))
        PontoResumo.query.filter(func.extract('year', PontoResumo.data_referencia) == ano, func.extract('month', PontoResumo.data_referencia) == mes).delete(synchronize_session=False)
        db.session.commit(); flash(f'Relatório de {mes_ref} zerado.')
    except Exception as e: db.session.rollback(); flash(f'Erro: {e}')
    return redirect(url_for('admin.admin_relatorio_folha'))
"""

# --- 3. TEMPLATE IMPORTAR CSV ---
FILE_IMPORTAR_CSV = """
{% extends 'base.html' %}
{% block content %}
<div class="max-w-2xl mx-auto">
    <div class="mb-6"><h2 class="text-2xl font-bold text-slate-800">Importar em Massa (CSV)</h2><p class="text-sm text-slate-500">Cadastre múltiplos funcionários de uma vez.</p></div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-8 mb-6">
        <form action="/admin/usuarios/importar-csv" method="POST" enctype="multipart/form-data" class="space-y-6">
            <div>
                <label class="label-pro">Arquivo CSV ou Excel (.csv)</label>
                <input type="file" name="arquivo_csv" accept=".csv" class="w-full text-sm text-slate-500 file:mr-4 file:py-2 file:px-4 file:rounded-full file:border-0 file:text-sm file:font-semibold file:bg-blue-50 file:text-blue-700 hover:file:bg-blue-100" required>
            </div>
            
            <div class="bg-slate-50 p-4 rounded-lg text-xs text-slate-500 border border-slate-200">
                <p class="font-bold mb-2">Formato Obrigatório do CSV (Separado por ponto e vírgula ';')</p>
                <code class="block bg-white p-2 rounded border border-slate-200">Nome;CPF;Cargo;Salario;Entrada;Saida</code>
                <p class="mt-2">Exemplo:</p>
                <code class="block bg-white p-2 rounded border border-slate-200">João Silva;12345678900;Assistente;2500,00;08:00;17:00</code>
            </div>

            <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-4 rounded-lg shadow-md transition">PROCESSAR ARQUIVO</button>
        </form>
    </div>
</div>
<style>.label-pro { display: block; font-size: 0.7rem; font-weight: 700; color: #64748b; text-transform: uppercase; margin-bottom: 0.5rem; }</style>
{% endblock %}
"""

# --- 4. TEMPLATE ADMIN USUARIOS (BOTAO IMPORTAR) ---
FILE_ADMIN_USUARIOS = """
{% extends 'base.html' %}
{% block content %}
<div class="flex items-center justify-between mb-6">
    <h2 class="text-2xl font-bold text-slate-800">Funcionários</h2>
</div>

<div class="grid grid-cols-2 gap-4 mb-8">
    <a href="/admin/usuarios/novo" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl shadow-md text-center transition transform hover:-translate-y-1">
        <i class="fas fa-user-plus mr-2"></i> NOVO CADASTRO
    </a>
    <a href="/admin/usuarios/importar-csv" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-4 rounded-xl shadow-md text-center transition transform hover:-translate-y-1">
        <i class="fas fa-file-csv mr-2"></i> IMPORTAR PLANILHA
    </a>
</div>

<div class="mb-6">
    <input type="text" id="buscaFunc" onkeyup="filtrarTabela('buscaFunc', 'listaFunc')" placeholder="Pesquisar funcionário..." class="w-full p-4 rounded-xl border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-blue-500">
</div>

{% if pendentes %}
<div class="bg-yellow-50 border border-yellow-200 rounded-xl overflow-hidden mb-8 shadow-sm">
    <div class="px-6 py-4 border-b border-yellow-200 bg-yellow-100/50 flex justify-between items-center">
        <h3 class="font-bold text-yellow-800"><i class="fas fa-clock mr-2"></i> Aguardando Cadastro ({{ pendentes|length }})</h3>
    </div>
    <div class="divide-y divide-yellow-200/50">
        {% for p in pendentes %}
        <div class="px-6 py-4 flex items-center justify-between hover:bg-yellow-100/30 transition">
            <div>
                <div class="font-bold text-slate-800">{{ p.nome_previsto }}</div>
                <div class="text-xs font-mono text-slate-500">CPF: {{ p.cpf }}</div>
                <div class="text-[10px] text-slate-400 mt-1">{{ p.cargo }}</div>
            </div>
            <a href="/admin/liberar-acesso/excluir/{{ p.id }}" class="text-red-400 hover:text-red-600 p-2" onclick="return confirm('Remover da lista de espera?')">
                <i class="fas fa-trash"></i>
            </a>
        </div>
        {% endfor %}
    </div>
</div>
{% endif %}

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="px-6 py-4 border-b border-slate-100 bg-slate-50/50 flex justify-between items-center">
        <h3 class="font-bold text-slate-700">Equipe Ativa</h3>
        <span class="text-xs bg-slate-200 text-slate-600 px-2 py-1 rounded-full font-bold">{{ users|length }}</span>
    </div>
    <div class="divide-y divide-slate-100" id="listaFunc">
        {% for u in users %}
        <div class="px-6 py-4 flex items-center justify-between hover:bg-slate-50 transition group item-lista">
            <div class="flex items-center gap-4">
                <div class="w-10 h-10 rounded-full flex items-center justify-center font-bold text-sm bg-slate-100 text-slate-600">
                    {{ u.real_name[:2].upper() }}
                </div>
                <div>
                    <div class="font-bold text-slate-800 nome-item">{{ u.real_name }}</div>
                    <div class="text-xs text-slate-500">{{ u.role }}</div>
                </div>
            </div>
            
            <div class="flex items-center gap-3">
                <span class="px-2 py-1 bg-emerald-100 text-emerald-700 text-[10px] font-bold uppercase rounded">Ativo</span>
                
                <a href="/admin/usuarios/editar/{{ u.id }}" class="w-8 h-8 flex items-center justify-center rounded-full text-slate-300 hover:bg-white hover:text-blue-600 hover:shadow border border-transparent hover:border-slate-200 transition">
                    <i class="fas fa-pencil-alt text-xs"></i>
                </a>
            </div>
        </div>
        {% endfor %}
    </div>
</div>
<script>
function filtrarTabela(inputId, listaId) {
    let input = document.getElementById(inputId);
    let filter = input.value.toUpperCase();
    let lista = document.getElementById(listaId);
    let itens = lista.getElementsByClassName('item-lista');
    for (let i = 0; i < itens.length; i++) {
        let nome = itens[i].getElementsByClassName('nome-item')[0];
        if (nome.innerHTML.toUpperCase().indexOf(filter) > -1) { itens[i].style.display = ""; } else { itens[i].style.display = "none"; }
    }
}
</script>
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
        print("\n>>> SUCESSO V47! <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V47: {PROJECT_NAME} ---")
    
    write_file("app/routes/holerites.py", FILE_BP_HOLERITES)
    write_file("app/routes/admin.py", FILE_BP_ADMIN)
    write_file("app/templates/admin_importar_csv.html", FILE_IMPORTAR_CSV)
    write_file("app/templates/admin_usuarios.html", FILE_ADMIN_USUARIOS)
    
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()



