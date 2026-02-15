import os
import shutil
import subprocess
from datetime import datetime

# ================= CONFIGURAÇÕES =================
PROJECT_DIR = os.getcwd()
BACKUP_ROOT = os.path.join(PROJECT_DIR, "backups_auto")
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
CURRENT_BACKUP_DIR = os.path.join(BACKUP_ROOT, f"bkp_updates_{TIMESTAMP}")

# Arquivos que serão modificados
FILES_TO_MODIFY = [
    "app/templates/ponto_registro.html",
    "app/ponto/templates/ponto/solicitar_ajuste.html",
    "app/ponto/routes.py",
    "app/ponto/templates/ponto/ponto_espelho.html"
]

def log(msg):
    print(f"\033[96m[UPDATE-SCRIPT]\033[0m {msg}")

def ensure_dir_exists(file_path):
    directory = os.path.dirname(file_path)
    if not os.path.exists(directory):
        os.makedirs(directory)

def create_backup():
    log("Criando backup de segurança...")
    if not os.path.exists(CURRENT_BACKUP_DIR):
        os.makedirs(CURRENT_BACKUP_DIR)
    
    for file_path in FILES_TO_MODIFY:
        full_path = os.path.join(PROJECT_DIR, file_path)
        if os.path.exists(full_path):
            dest_path = os.path.join(CURRENT_BACKUP_DIR, file_path)
            ensure_dir_exists(dest_path)
            shutil.copy2(full_path, dest_path)

def apply_fixes():
    log("Aplicando correções (Histórico, CSRF e Tradução)...")

    # ---------------------------------------------------------
    # 1. PONTO REGISTRO (Adicionando Histórico + CSRF)
    # ---------------------------------------------------------
    content_registro = """{% extends 'base.html' %}
{% block content %}
<div class="max-w-md mx-auto text-center">
    <div class="mb-8">
        <h2 class="text-2xl font-bold text-slate-800">Registrar Ponto</h2>
        <p class="text-sm text-slate-500">Confirme sua localização.</p>
    </div>

    {% if bloqueado %}
    <div class="bg-red-50 border-l-4 border-red-500 p-6 rounded-r-xl shadow-md text-left mb-8">
        <h3 class="text-lg font-bold text-red-700 flex items-center gap-2"><i class="fas fa-ban"></i> AÇÃO BLOQUEADA</h3>
        <p class="text-sm text-red-600 mt-2">{{ motivo }}</p>
    </div>
    {% else %}
    <div class="bg-slate-900 text-white rounded-2xl p-8 shadow-2xl mb-8 border border-slate-700 relative overflow-hidden">
        <div class="text-5xl font-mono font-bold tracking-widest mb-2" id="relogio">--:--:--</div>
        <div class="text-sm text-slate-400 uppercase tracking-widest" id="data-hoje">...</div>
        <div class="mt-6 inline-block bg-blue-600 text-xs font-bold px-4 py-1 rounded-full uppercase tracking-wide shadow-lg animate-pulse">
            Localizando...
        </div>
    </div>
    
    <form action="/ponto/registrar" method="POST" id="formPonto">
        <!-- TOKEN CSRF OBRIGATÓRIO -->
        <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
        
        <input type="hidden" name="tipo" id="inputTipo">
        <input type="hidden" name="lat" id="lat">
        <input type="hidden" name="lon" id="lon">
        
        <div class="grid grid-cols-2 gap-4 mb-4">
            <button type="button" onclick="submitPonto('Entrada')" class="bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-4 rounded-xl shadow-lg transition transform active:scale-95">
                <i class="fas fa-sign-in-alt mb-1 block text-2xl"></i> ENTRADA
            </button>
            <button type="button" onclick="submitPonto('Saída')" class="bg-red-600 hover:bg-red-700 text-white font-bold py-4 rounded-xl shadow-lg transition transform active:scale-95">
                <i class="fas fa-sign-out-alt mb-1 block text-2xl"></i> SAÍDA
            </button>
            <button type="button" onclick="submitPonto('Ida Almoço')" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl shadow-lg transition transform active:scale-95">
                <i class="fas fa-utensils mb-1 block text-2xl"></i> IDA ALMOÇO
            </button>
            <button type="button" onclick="submitPonto('Volta Almoço')" class="bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-xl shadow-lg transition transform active:scale-95">
                <i class="fas fa-undo mb-1 block text-2xl"></i> VOLTA ALMOÇO
            </button>
        </div>
        <p id="geoStatus" class="text-xs text-slate-400 mt-2 h-4"></p>
    </form>
    {% endif %}

    <!-- HISTÓRICO DO DIA (SOLICITADO) -->
    <div class="mt-8 text-left">
        <h3 class="text-xs font-bold text-slate-400 uppercase mb-3 ml-1">Histórico de Hoje</h3>
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden divide-y divide-slate-100">
            {% for p in registros %}
            <div class="px-4 py-3 flex justify-between items-center hover:bg-slate-50 transition">
                <span class="text-sm font-bold text-slate-700 flex items-center gap-2">
                    <i class="fas fa-circle text-[8px] {% if 'Entrada' in p.tipo or 'Volta' in p.tipo %}text-emerald-500{% else %}text-red-500{% endif %}"></i>
                    {{ p.tipo }}
                </span>
                <span class="text-sm font-mono text-slate-500 font-bold bg-slate-100 px-2 py-1 rounded">{{ p.hora_registro.strftime('%H:%M') }}</span>
            </div>
            {% else %}
            <div class="p-6 text-center text-xs text-slate-400 flex flex-col items-center">
                <i class="fas fa-clock text-2xl mb-2 opacity-30"></i>
                Nenhum registro hoje.
            </div>
            {% endfor %}
        </div>
    </div>
</div>

<script>
    function updateTime() { 
        const now = new Date();
        document.getElementById('relogio').innerText = now.toLocaleTimeString('pt-BR'); 
        document.getElementById('data-hoje').innerText = now.toLocaleDateString('pt-BR', {weekday: 'long', day: 'numeric', month: 'long'});
    }
    setInterval(updateTime, 1000); updateTime();

    function submitPonto(tipo) {
        const btn = event.currentTarget;
        const st = document.getElementById('geoStatus');
        const form = document.getElementById('formPonto');
        
        document.getElementById('inputTipo').value = tipo;
        
        // Bloqueia botões
        const btns = document.querySelectorAll('button');
        btns.forEach(b => b.disabled = true);
        st.innerText = "Obtendo localização GPS...";
        st.className = "text-xs text-blue-500 mt-2 h-4 animate-pulse font-bold";

        if (navigator.geolocation) {
            navigator.geolocation.getCurrentPosition(
                (p) => { 
                    document.getElementById('lat').value = p.coords.latitude; 
                    document.getElementById('lon').value = p.coords.longitude; 
                    st.innerText = "Localização obtida! Enviando...";
                    st.className = "text-xs text-emerald-600 mt-2 h-4 font-bold";
                    form.submit(); 
                },
                (e) => { 
                    alert("Erro ao obter GPS: " + e.message); 
                    st.innerText = "Erro no GPS.";
                    st.className = "text-xs text-red-500 mt-2 h-4";
                    btns.forEach(b => b.disabled = false);
                },
                { enableHighAccuracy: true, timeout: 10000 }
            );
        } else {
            alert("Seu dispositivo não suporta GPS.");
            btns.forEach(b => b.disabled = false);
        }
    }
</script>
{% endblock %}
"""
    fpath_registro = os.path.join(PROJECT_DIR, "app/templates/ponto_registro.html")
    with open(fpath_registro, "w", encoding="utf-8") as f:
        f.write(content_registro)

    # ---------------------------------------------------------
    # 2. SOLICITAR AJUSTE (Adicionando CSRF Token)
    # ---------------------------------------------------------
    content_ajuste = """{% extends 'base.html' %}
{% block content %}
<div class="max-w-2xl mx-auto">
    <div class="mb-6"><h2 class="text-xl font-bold text-slate-800">Solicitar Ajuste</h2><p class="text-sm text-slate-500">Gestão de ponto.</p></div>

    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-6">
        <form action="/ponto/solicitar-ajuste" method="POST" class="flex gap-4 items-end">
            <!-- TOKEN CSRF INJETADO -->
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
            
            <div class="flex-1">
                <label class="block text-xs font-bold text-slate-500 uppercase mb-2">Data do Ponto</label>
                <input type="date" name="data_busca" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3" required>
            </div>
            <button type="submit" name="acao" value="buscar" class="bg-blue-600 text-white font-bold py-3 px-6 rounded-lg shadow hover:bg-blue-700 transition"><i class="fas fa-search"></i></button>
        </form>
    </div>

    {% if data_sel %}
    <div class="bg-white rounded-xl border border-slate-200 shadow-sm p-6 mb-8 animate-fade-in">
        <div class="flex justify-between items-center mb-4 border-b pb-2">
            <h3 class="font-bold text-slate-800">Registros em {{ data_sel.strftime('%d/%m/%Y') }}</h3>
            <button onclick="abrirInclusao()" class="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-3 py-1 rounded font-bold transition"><i class="fas fa-plus mr-1"></i> ADICIONAR NOVO</button>
        </div>
        <div class="space-y-2 mb-6">
            {% for p in pontos %}
            <div class="flex justify-between items-center p-3 bg-slate-50 rounded-lg border border-slate-100">
                <div><span class="text-xs font-bold text-slate-500 block">{{ p.tipo }}</span><span class="font-mono font-bold text-slate-800">{{ p.hora_registro.strftime('%H:%M') }}</span></div>
                <div class="flex gap-2">
                    <button onclick="abrirEdicao('{{ p.id }}', '{{ p.hora_registro.strftime('%H:%M') }}', '{{ p.tipo }}')" class="text-[10px] bg-blue-50 text-blue-600 font-bold px-2 py-1 rounded hover:bg-blue-100">EDITAR</button>
                    <button onclick="abrirExclusao('{{ p.id }}', '{{ p.hora_registro.strftime('%H:%M') }}')" class="text-[10px] bg-red-50 text-red-600 font-bold px-2 py-1 rounded hover:bg-red-100">EXCLUIR</button>
                </div>
            </div>
            {% else %}<p class="text-xs text-slate-400 italic">Sem registros neste dia.</p>{% endfor %}
        </div>

        <div id="formContainer" class="hidden bg-slate-50 p-4 rounded-xl border border-blue-200 shadow-inner">
            <h3 class="font-bold text-blue-700 mb-4 text-sm uppercase" id="formTitle">Detalhes</h3>
            <form action="/ponto/solicitar-ajuste" method="POST" class="space-y-4">
                <!-- TOKEN CSRF INJETADO -->
                <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
                
                <input type="hidden" name="acao" value="enviar">
                <input type="hidden" name="data_ref" value="{{ data_sel }}">
                <input type="hidden" name="ponto_id" id="form_ponto_id"> 
                <input type="hidden" name="tipo_solicitacao" id="form_tipo_solic"> 
                <div class="grid grid-cols-2 gap-4" id="divHorarioTipo">
                    <div><label class="block text-xs font-bold text-slate-500 uppercase mb-2">Horário</label><input type="time" name="novo_horario" id="form_horario" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 font-mono"></div>
                    <div><label class="block text-xs font-bold text-slate-500 uppercase mb-2">Tipo</label><select name="tipo_batida" id="form_tipo" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 text-sm"><option value="Entrada">Entrada</option><option value="Ida Almoço">Ida Almoço</option><option value="Volta Almoço">Volta Almoço</option><option value="Saída">Saída</option></select></div>
                </div>
                <div><label class="block text-xs font-bold text-slate-500 uppercase mb-2">Justificativa</label><textarea name="justificativa" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-2 text-sm" rows="2" required></textarea></div>
                <div class="flex gap-2"><button type="button" onclick="fecharForm()" class="flex-1 bg-slate-200 text-slate-600 font-bold py-2 rounded-lg text-xs">CANCELAR</button><button type="submit" class="flex-1 bg-blue-600 hover:bg-blue-700 text-white font-bold py-2 rounded-lg shadow text-xs">ENVIAR</button></div>
            </form>
        </div>
    </div>
    {% endif %}

    <div class="mt-8">
        <h3 class="font-bold text-slate-700 text-sm mb-4 border-b pb-2">Meus Pedidos Recentes</h3>
        <div class="space-y-3">
            {% for req in meus_ajustes %}
            <div class="bg-white border border-slate-200 rounded-lg p-4 shadow-sm relative pl-4 border-l-4 {% if req.status == 'Aprovado' %} border-l-emerald-500 {% elif req.status == 'Reprovado' %} border-l-red-500 {% else %} border-l-yellow-500 {% endif %}">
                <div class="flex justify-between items-start mb-2">
                    <span class="text-[10px] font-bold uppercase text-slate-400">{{ req.data_referencia.strftime('%d/%m') }} - {{ req.tipo_solicitacao }}</span>
                    <span class="text-[10px] font-bold uppercase px-2 py-0.5 rounded {% if req.status == 'Pendente' %} bg-yellow-100 text-yellow-700 {% elif req.status == 'Aprovado' %} bg-emerald-100 text-emerald-700 {% else %} bg-red-100 text-red-700 {% endif %}">{{ req.status }}</span>
                </div>
                
                <div class="grid grid-cols-2 gap-2 text-xs mb-2 bg-slate-50 p-2 rounded">
                    <div><span class="block text-slate-400">Horário Antigo</span><strong class="font-mono text-slate-600">{{ extras.get(req.id, '-') }}</strong></div>
                    <div><span class="block text-slate-400">Horário Novo</span><strong class="font-mono text-blue-600">{% if req.novo_horario %}{{ req.novo_horario }} ({{ req.tipo_batida }}){% else %} - {% endif %}</strong></div>
                </div>

                <div class="text-xs text-slate-500 italic mb-2">Justificativa: "{{ req.justificativa }}"</div>
                {% if req.status == 'Reprovado' %}<div class="bg-red-50 p-2 rounded border border-red-100 text-xs text-red-700"><strong>Devolutiva:</strong> {{ req.motivo_reprovacao }}</div>{% endif %}
            </div>
            {% else %}<p class="text-center text-xs text-slate-400 py-4">Nenhum pedido recente.</p>{% endfor %}
        </div>
    </div>
</div>
<script>
    function abrirInclusao() { resetForm(); document.getElementById('formTitle').innerText = "INCLUIR"; document.getElementById('form_tipo_solic').value = "Inclusao"; document.getElementById('formContainer').classList.remove('hidden'); }
    function abrirEdicao(id, hora, tipo) { resetForm(); document.getElementById('formTitle').innerText = "EDITAR"; document.getElementById('form_ponto_id').value = id; document.getElementById('form_horario').value = hora; document.getElementById('form_tipo').value = tipo; document.getElementById('form_tipo_solic').value = "Edicao"; document.getElementById('formContainer').classList.remove('hidden'); }
    function abrirExclusao(id, hora) { resetForm(); document.getElementById('formTitle').innerText = "EXCLUIR"; document.getElementById('form_ponto_id').value = id; document.getElementById('form_tipo_solic').value = "Exclusao"; document.getElementById('divHorarioTipo').classList.add('hidden'); document.getElementById('formContainer').classList.remove('hidden'); }
    function resetForm() { document.getElementById('form_ponto_id').value = ""; document.getElementById('form_horario').value = ""; document.getElementById('divHorarioTipo').classList.remove('hidden'); }
    function fecharForm() { document.getElementById('formContainer').classList.add('hidden'); }
</script>
{% endblock %}
"""
    fpath_ajuste = os.path.join(PROJECT_DIR, "app/ponto/templates/ponto/solicitar_ajuste.html")
    with open(fpath_ajuste, "w", encoding="utf-8") as f:
        f.write(content_ajuste)

    # ---------------------------------------------------------
    # 3. ROUTES (Adicionando tradução dos dias da semana)
    # ---------------------------------------------------------
    content_routes = """from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.extensions import db
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm
from datetime import datetime, date
from sqlalchemy import func

ponto_bp = Blueprint('ponto', __name__, template_folder='templates', url_prefix='/ponto')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    hoje = get_brasil_time().date()
    if request.method == 'POST':
        tipo = request.form.get('tipo')
        lat = request.form.get('lat')
        lon = request.form.get('lon')
        
        # Validação simples
        if not tipo:
            flash('Selecione um tipo de registro.', 'error')
            return redirect(url_for('ponto.registrar_ponto'))

        novo = PontoRegistro(
            user_id=current_user.id, 
            data_registro=hoje, 
            tipo=tipo, 
            latitude=lat, 
            longitude=lon
        )
        db.session.add(novo)
        try:
            db.session.commit()
            calcular_dia(current_user.id, hoje)
            flash(f'Ponto de {tipo} registrado com sucesso!', 'success')
        except Exception as e:
            db.session.rollback()
            flash(f'Erro ao registrar: {str(e)}', 'error')
            
        return redirect(url_for('main.dashboard'))
    
    # Busca histórico do dia para exibir
    registros = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    return render_template('ponto_registro.html', registros=registros)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master':
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try:
        ano, mes = map(int, mes_ref.split('-'))
    except:
        hoje = get_brasil_time()
        ano, mes = hoje.year, hoje.month
        mes_ref = hoje.strftime('%Y-%m')
    
    resumos = PontoResumo.query.filter(
        PontoResumo.user_id == target_user_id,
        func.extract('year', PontoResumo.data_referencia) == ano,
        func.extract('month', PontoResumo.data_referencia) == mes
    ).order_by(PontoResumo.data_referencia).all()
    
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]

    # Dicionário de Tradução dos Dias (Fix para idioma Inglês no Server)
    dias_semana = {0: 'Seg', 1: 'Ter', 2: 'Qua', 3: 'Qui', 4: 'Sex', 5: 'Sáb', 6: 'Dom'}

    return render_template('ponto/ponto_espelho.html', 
                         resumos=resumos, 
                         user=user, 
                         detalhes=detalhes, 
                         format_hm=format_minutes_to_hm, 
                         mes_ref=mes_ref,
                         dias_semana=dias_semana)

@ponto_bp.route('/solicitar-ajuste', methods=['GET', 'POST'])
@login_required
def solicitar_ajuste():
    data_sel = None
    pontos = []
    
    if request.method == 'POST':
        acao = request.form.get('acao')
        
        if acao == 'buscar':
            data_busca = request.form.get('data_busca')
            if data_busca:
                try:
                    data_sel = datetime.strptime(data_busca, '%Y-%m-%d').date()
                    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_sel).order_by(PontoRegistro.hora_registro).all()
                except:
                    flash('Data inválida.', 'error')
        
        elif acao == 'enviar':
            try:
                # Logica simplificada de ajuste (expansível)
                ajuste = PontoAjuste(
                    user_id=current_user.id,
                    data_referencia=request.form.get('data_ref'),
                    ponto_original_id=request.form.get('ponto_id') or None,
                    novo_horario=request.form.get('novo_horario'),
                    tipo_batida=request.form.get('tipo_batida'),
                    tipo_solicitacao=request.form.get('tipo_solicitacao'),
                    justificativa=request.form.get('justificativa')
                )
                db.session.add(ajuste)
                db.session.commit()
                flash('Solicitação enviada!', 'success')
                return redirect(url_for('ponto.solicitar_ajuste'))
            except Exception as e:
                db.session.rollback()
                flash(f'Erro: {e}', 'error')

    # Histórico de Ajustes
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(10).all()
    extras = {}
    for a in meus_ajustes:
        if a.ponto_original_id:
            p = PontoRegistro.query.get(a.ponto_original_id)
            if p: extras[a.id] = f"{p.hora_registro.strftime('%H:%M')} ({p.tipo})"
    
    return render_template('ponto/solicitar_ajuste.html', 
                         data_sel=data_sel, 
                         pontos=pontos, 
                         meus_ajustes=meus_ajustes, 
                         extras=extras)
"""
    fpath_routes = os.path.join(PROJECT_DIR, "app/ponto/routes.py")
    with open(fpath_routes, "w", encoding="utf-8") as f:
        f.write(content_routes)

    # ---------------------------------------------------------
    # 4. PONTO ESPELHO (Usando a tradução)
    # ---------------------------------------------------------
    content_espelho = """{% extends 'base.html' %}
{% block content %}
<div class="mb-6 flex justify-between items-center">
    <div>
        <h2 class="text-2xl font-bold text-slate-800">Espelho de Ponto</h2>
        <p class="text-sm text-slate-500">Colaborador: <span class="font-bold text-slate-700">{{ user.real_name }}</span></p>
    </div>
    <div class="text-right">
        <span class="text-xs font-bold text-slate-400 uppercase">Período</span>
        <div class="font-bold text-slate-700">{{ mes_ref }}</div>
    </div>
</div>

<div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
    <div class="overflow-x-auto">
        <table class="w-full text-left text-sm">
            <thead class="bg-slate-50 text-slate-400 font-bold text-xs uppercase border-b border-slate-100">
                <tr>
                    <th class="px-4 py-4">Data</th>
                    <th class="px-4 py-4">Batidas Realizadas</th>
                    <th class="px-4 py-4 text-center">Trabalhado</th>
                    <th class="px-4 py-4 text-center">Saldo</th>
                    <th class="px-4 py-4 text-right">Status</th>
                </tr>
            </thead>
            <tbody class="divide-y divide-slate-100">
                {% for r in resumos %}
                <tr class="hover:bg-slate-50 transition cursor-help" onclick="toggleDetails('det-{{ r.id }}')">
                    <!-- DATA TRADUZIDA AQUI -->
                    <td class="px-4 py-4 font-medium text-slate-700">
                        {{ r.data_referencia.strftime('%d/%m') }} 
                        <span class="text-slate-400 text-xs uppercase ml-1">
                            ({{ dias_semana[r.data_referencia.weekday()] }})
                        </span>
                    </td>
                    <td class="px-4 py-4">
                        <div class="flex flex-wrap gap-1">
                            {% for b in detalhes[r.id] %}
                            <span class="bg-slate-100 text-slate-600 px-2 py-0.5 rounded text-[10px] font-bold border border-slate-200">{{ b }}</span>
                            {% endfor %}
                        </div>
                    </td>
                    <td class="px-4 py-4 text-center font-mono">{{ format_hm(r.minutos_trabalhados) }}</td>
                    <td class="px-4 py-4 text-center font-mono font-bold {% if r.minutos_saldo >= 0 %} text-emerald-600 {% else %} text-red-500 {% endif %}">
                        {{ format_hm(r.minutos_saldo) }}
                    </td>
                    <td class="px-4 py-4 text-right">
                        <span class="text-[10px] font-bold uppercase px-2 py-1 rounded-full 
                            {% if r.status_dia == 'OK' %} bg-emerald-50 text-emerald-600 
                            {% elif r.status_dia == 'Incompleto' %} bg-amber-50 text-amber-600 
                            {% elif r.status_dia == 'Falta' %} bg-red-50 text-red-600 
                            {% else %} bg-blue-50 text-blue-600 {% endif %}">
                            {{ r.status_dia }}
                        </span>
                    </td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</div>
<div class="mt-4 text-center text-xs text-slate-400">
    <i class="fas fa-info-circle mr-1"></i> Batidas ímpares são marcadas como "Incompleto" e não somam horas.
</div>
{% endblock %}
"""
    fpath_espelho = os.path.join(PROJECT_DIR, "app/ponto/templates/ponto/ponto_espelho.html")
    with open(fpath_espelho, "w", encoding="utf-8") as f:
        f.write(content_espelho)

    log("Todas as alterações aplicadas.")

def git_operations():
    log("Enviando para o Git...")
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Fix: CSRF in Adjustments, Point History and PT-BR Dates"], check=True)
        subprocess.run(["git", "push"], check=True)
        log("Sucesso.")
    except Exception as e:
        log(f"Erro Git: {e}")

def self_destruct():
    try:
        os.remove(__file__)
    except: pass

if __name__ == "__main__":
    create_backup()
    apply_fixes()
    git_operations()
    self_destruct()


