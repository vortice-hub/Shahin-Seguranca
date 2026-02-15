import os
import sys
import subprocess

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V72: QR Code Maior, Feedback no Terminal e Atualizacao Automatica no Celular"

# --- 1. APP/ROUTES/PONTO.PY (Adicionando API de Verificação de Status) ---
FILE_BP_PONTO = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm, data_por_extenso
from datetime import datetime, date, timedelta
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

ponto_bp = Blueprint('ponto', __name__, template_folder='templates', url_prefix='/ponto')

# --- APIS DO SISTEMA DE PONTO ---

@ponto_bp.route('/api/gerar-token', methods=['GET'])
@login_required
def gerar_token_qrcode():
    if current_user.role == 'Terminal': return jsonify({'error': 'Terminal não gera token'}), 403
    s = URLSafeTimedSerializer(current_app.secret_key)
    token = s.dumps({'user_id': current_user.id, 'timestamp': get_brasil_time().timestamp()})
    return jsonify({'token': token})

@ponto_bp.route('/api/check-status', methods=['GET'])
@login_required
def check_status_ponto():
    # Verifica se houve um ponto registrado nos ultimos 10 segundos
    # Isso permite que o celular do funcionario saiba que o terminal leu o codigo
    if current_user.role == 'Terminal': return jsonify({'status': 'ignorar'})
    
    agora = get_brasil_time()
    # Busca ultimo ponto do usuario
    ultimo_ponto = PontoRegistro.query.filter_by(user_id=current_user.id).order_by(PontoRegistro.id.desc()).first()
    
    if ultimo_ponto:
        # Pega data/hora do ponto
        dt_ponto = datetime.combine(ultimo_ponto.data_registro, ultimo_ponto.hora_registro)
        # Se foi registrado ha menos de 10 segundos
        diferenca = (agora - dt_ponto).total_seconds()
        
        if diferenca < 15: # Janela de tempo para notificar
            return jsonify({
                'marcado': True, 
                'tipo': ultimo_ponto.tipo, 
                'hora': ultimo_ponto.hora_registro.strftime('%H:%M')
            })
            
    return jsonify({'marcado': False})

@ponto_bp.route('/api/registrar-leitura', methods=['POST'])
@login_required
def registrar_leitura_terminal():
    if current_user.role != 'Terminal' and current_user.role != 'Master': return jsonify({'error': 'Acesso negado.'}), 403
    data = request.json
    token = data.get('token')
    if not token: return jsonify({'error': 'Token vazio'}), 400
    s = URLSafeTimedSerializer(current_app.secret_key)
    try:
        dados = s.loads(token, max_age=35)
        user_alvo = User.query.get(dados['user_id'])
        if not user_alvo: return jsonify({'error': 'Usuário inválido'}), 404
        
        hoje = get_brasil_time().date()
        
        # Verifica duplicidade imediata (evita leitura dupla em 1 min)
        ultimo = PontoRegistro.query.filter_by(user_id=user_alvo.id, data_registro=hoje).order_by(PontoRegistro.hora_registro.desc()).first()
        if ultimo:
            agora_time = get_brasil_time()
            dt_ultimo = datetime.combine(hoje, ultimo.hora_registro)
            if (agora_time - dt_ultimo).total_seconds() < 60:
                 return jsonify({'error': f'Ponto já registrado há instantes ({ultimo.hora_registro.strftime("%H:%M")}). Aguarde.'}), 400

        pontos_hoje = PontoRegistro.query.filter_by(user_id=user_alvo.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
        
        proxima = "Entrada"
        if len(pontos_hoje) == 1: proxima = "Ida Almoço"
        elif len(pontos_hoje) == 2: proxima = "Volta Almoço"
        elif len(pontos_hoje) == 3: proxima = "Saída"
        elif len(pontos_hoje) >= 4: proxima = "Extra"
        
        novo = PontoRegistro(user_id=user_alvo.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=proxima, latitude='QR-Code', longitude='Presencial')
        db.session.add(novo); db.session.commit(); calcular_dia(user_alvo.id, hoje)
        
        return jsonify({'success': True, 'message': f'Ponto registrado: {proxima}', 'funcionario': user_alvo.real_name, 'hora': novo.hora_registro.strftime('%H:%M'), 'tipo': proxima})
    except SignatureExpired: return jsonify({'error': 'QR Code expirado.'}), 400
    except BadSignature: return jsonify({'error': 'QR Code inválido.'}), 400
    except Exception as e: return jsonify({'error': f'Erro interno: {str(e)}'}), 500

# --- ROTAS DE INTERFACE ---

@ponto_bp.route('/scanner')
@login_required
def terminal_scanner():
    if current_user.role != 'Terminal' and current_user.role != 'Master':
        flash('Acesso restrito.')
        return redirect(url_for('main.dashboard'))
    return render_template('ponto/terminal_leitura.html')

@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    if current_user.role == 'Terminal': return redirect(url_for('ponto.terminal_scanner'))

    hoje = get_brasil_time().date()
    hoje_extenso = data_por_extenso(hoje)
    
    bloqueado = False; motivo = ""
    if current_user.escala == '5x2' and hoje.weekday() >= 5: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."
    elif current_user.escala == '12x36' and current_user.data_inicio_escala:
        if (hoje - current_user.data_inicio_escala).days % 2 != 0: bloqueado = True; motivo = "Não é possível realizar a marcação de ponto."

    pontos = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
    prox = "Entrada"
    if len(pontos) == 1: prox = "Ida Almoço"
    elif len(pontos) == 2: prox = "Volta Almoço"
    elif len(pontos) == 3: prox = "Saída"
    elif len(pontos) >= 4: prox = "Extra"

    if request.method == 'POST':
        if bloqueado: flash('Bloqueado'); return redirect(url_for('main.dashboard'))
        db.session.add(PontoRegistro(user_id=current_user.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=prox, latitude=request.form.get('latitude'), longitude=request.form.get('longitude')))
        db.session.commit(); calcular_dia(current_user.id, hoje)
        return redirect(url_for('main.dashboard'))
    
    return render_template('ponto/registro.html', proxima_acao=prox, hoje_extenso=hoje_extenso, pontos=pontos, bloqueado=bloqueado, motivo=motivo, hoje=hoje)

@ponto_bp.route('/espelho')
@login_required
def espelho_ponto():
    target_user_id = request.args.get('user_id', type=int) or current_user.id
    if target_user_id != current_user.id and current_user.role != 'Master':
        return redirect(url_for('main.dashboard'))
    
    user = User.query.get_or_404(target_user_id)
    mes_ref = request.args.get('mes_ref') or get_brasil_time().strftime('%Y-%m')
    try: ano, mes = map(int, mes_ref.split('-'))
    except: hoje = get_brasil_time(); ano, mes = hoje.year, hoje.month; mes_ref = hoje.strftime('%Y-%m')
    
    resumos = PontoResumo.query.filter(
        PontoResumo.user_id == target_user_id,
        func.extract('year', PontoResumo.data_referencia) == ano,
        func.extract('month', PontoResumo.data_referencia) == mes
    ).order_by(PontoResumo.data_referencia).all()
    
    detalhes = {}
    for r in resumos:
        batidas = PontoRegistro.query.filter_by(user_id=target_user_id, data_registro=r.data_referencia).order_by(PontoRegistro.hora_registro).all()
        detalhes[r.id] = [b.hora_registro.strftime('%H:%M') for b in batidas]

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
    pontos_dia = []; data_selecionada = None
    meus_ajustes = PontoAjuste.query.filter_by(user_id=current_user.id).order_by(PontoAjuste.created_at.desc()).limit(20).all()
    if request.method == 'POST':
        if request.form.get('acao') == 'buscar':
            try: data_selecionada = datetime.strptime(request.form.get('data_busca'), '%Y-%m-%d').date(); pontos_dia = PontoRegistro.query.filter_by(user_id=current_user.id, data_registro=data_selecionada).order_by(PontoRegistro.hora_registro).all()
            except: flash('Data inválida')
        elif request.form.get('acao') == 'enviar':
            try:
                dt_obj = datetime.strptime(request.form.get('data_ref'), '%Y-%m-%d').date()
                p_id = int(request.form.get('ponto_id')) if request.form.get('ponto_id') else None
                solic = PontoAjuste(user_id=current_user.id, data_referencia=dt_obj, ponto_original_id=p_id, novo_horario=request.form.get('novo_horario'), tipo_batida=request.form.get('tipo_batida'), tipo_solicitacao=request.form.get('tipo_solicitacao'), justificativa=request.form.get('justificativa'))
                db.session.add(solic); db.session.commit(); flash('Enviado!')
                return redirect(url_for('ponto.solicitar_ajuste'))
            except: pass
    dados_extras = {}
    for p in meus_ajustes:
        if p.ponto_original_id:
            original = PontoRegistro.query.get(p.ponto_original_id)
            if original: dados_extras[p.id] = original.hora_registro.strftime('%H:%M')
    return render_template('ponto/solicitar_ajuste.html', pontos=pontos_dia, data_sel=data_selecionada, meus_ajustes=meus_ajustes, extras=dados_extras)
"""

# --- 2. TEMPLATE REGISTRO.HTML (QR Code Gigante + Polling) ---
FILE_PONTO_REGISTRO = """
{% extends 'base.html' %}
{% block content %}
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>

<div class="max-w-md mx-auto text-center">
    
    <div class="mb-4">
        <h2 class="text-2xl font-bold text-slate-800">Meu Ponto</h2>
        <p class="text-sm text-slate-500">Aproxime este código do Terminal na portaria.</p>
    </div>

    {% if bloqueado %}
    <div class="bg-red-50 border-l-4 border-red-500 p-6 rounded-r-xl shadow-md text-left mb-8">
        <h3 class="text-lg font-bold text-red-700 flex items-center gap-2"><i class="fas fa-ban"></i> AÇÃO BLOQUEADA</h3>
        <p class="text-sm text-red-600 mt-2">{{ motivo }}</p>
    </div>
    {% else %}
    
    <div class="bg-white rounded-3xl shadow-xl border border-slate-200 p-8 relative overflow-hidden">
        <div class="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-blue-500 to-purple-600"></div>

        <div class="mb-4">
            <h3 class="text-xl font-bold text-slate-800">{{ current_user.real_name }}</h3>
            <p class="text-xs text-slate-400 font-mono uppercase">{{ current_user.role }}</p>
        </div>

        <!-- QR Code Gigante -->
        <div class="flex justify-center mb-6">
            <div id="qrcode" class="p-2 border-4 border-slate-900 rounded-xl bg-white"></div>
        </div>

        <div class="w-full bg-slate-100 rounded-full h-2.5 mb-2">
            <div id="progressBar" class="bg-blue-600 h-2.5 rounded-full transition-all duration-1000 ease-linear" style="width: 100%"></div>
        </div>
        <p class="text-xs text-slate-400 font-mono" id="statusToken">Atualizando em <span id="countdown">30</span>s...</p>

        <div class="mt-6 pt-6 border-t border-slate-100 flex justify-between items-center">
            <div class="text-left">
                <span class="block text-[10px] font-bold text-slate-400 uppercase">Próximo Ponto</span>
                <span class="text-sm font-bold text-blue-600">{{ proxima_acao }}</span>
            </div>
            <div class="text-right">
                <span class="block text-[10px] font-bold text-slate-400 uppercase">Hoje</span>
                <span class="text-sm font-mono text-slate-600">{{ hoje.strftime('%d/%m') }}</span>
            </div>
        </div>
    </div>
    {% endif %}

    <div class="mt-8 text-left">
        <h3 class="text-xs font-bold text-slate-400 uppercase mb-3 ml-1">Batidas de Hoje</h3>
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden divide-y divide-slate-100">
            {% for p in pontos %}
            <div class="px-4 py-3 flex justify-between items-center">
                <span class="text-sm font-bold text-slate-700 flex items-center gap-2">
                    <i class="fas fa-circle text-[6px] {% if 'Entrada' in p.tipo %}text-emerald-500{% else %}text-amber-500{% endif %}"></i>
                    {{ p.tipo }}
                </span>
                <span class="text-sm font-mono text-slate-500 font-bold bg-slate-50 px-2 py-1 rounded">{{ p.hora_registro.strftime('%H:%M') }}</span>
            </div>
            {% else %}
            <div class="p-6 text-center text-xs text-slate-400">Ainda não iniciou a jornada.</div>
            {% endfor %}
        </div>
    </div>
</div>

<script>
    let timerInterval;
    const TIME_LIMIT = 30; 
    let timeLeft = TIME_LIMIT;

    function generateQRCode() {
        fetch('/ponto/api/gerar-token')
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    document.getElementById('qrcode').innerHTML = `<p class="text-red-500 text-xs">${data.error}</p>`;
                    return;
                }
                const container = document.getElementById("qrcode");
                container.innerHTML = "";
                // AUMENTADO PARA 260px (Mais facil de ler)
                new QRCode(container, {
                    text: data.token,
                    width: 260,
                    height: 260,
                    colorDark : "#000000",
                    colorLight : "#ffffff",
                    correctLevel : QRCode.CorrectLevel.L // Low correction = menos pixels = mais facil ler
                });
                resetTimer();
            })
            .catch(err => { console.error("Erro:", err); });
    }

    function resetTimer() {
        timeLeft = TIME_LIMIT;
        clearInterval(timerInterval);
        const bar = document.getElementById("progressBar");
        const text = document.getElementById("countdown");

        timerInterval = setInterval(() => {
            timeLeft--;
            text.innerText = timeLeft;
            const pct = (timeLeft / TIME_LIMIT) * 100;
            bar.style.width = pct + "%";
            if (timeLeft <= 0) generateQRCode();
        }, 1000);
    }
    
    // Polling: Verifica se o ponto foi batido a cada 2 segundos
    setInterval(() => {
        {% if not bloqueado %}
        fetch('/ponto/api/check-status')
            .then(r => r.json())
            .then(data => {
                if (data.marcado) {
                    // Feedback Visual e Redirect
                    document.body.innerHTML = `
                        <div class="flex h-screen items-center justify-center bg-emerald-600 text-white flex-col">
                            <i class="fas fa-check-circle text-6xl mb-4 animate-bounce"></i>
                            <h1 class="text-3xl font-bold">PONTO REGISTRADO!</h1>
                            <p class="text-lg mt-2">${data.tipo} às ${data.hora}</p>
                            <p class="text-sm mt-4 opacity-80">Redirecionando...</p>
                        </div>
                    `;
                    setTimeout(() => { window.location.href = '/'; }, 3000);
                }
            });
        {% endif %}
    }, 2000);

    document.addEventListener("DOMContentLoaded", () => {
        {% if not bloqueado %} generateQRCode(); {% endif %}
    });
</script>
{% endblock %}
"""

# --- 3. TEMPLATE TERMINAL (COM MODAL E FEEDBACK) ---
FILE_TERMINAL_HTML = """
{% extends 'base.html' %}
{% block content %}
<script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
<style>
    .terminal-mode { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #0f172a; z-index: 9999; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; }
    #reader { width: 100%; max-width: 600px; border-radius: 20px; overflow: hidden; border: 4px solid #3b82f6; background: black; }
    
    /* MODAL OVERLAY */
    #successModal {
        position: fixed; top: 0; left: 0; width: 100%; height: 100%;
        background: rgba(0,0,0,0.9);
        display: flex; align-items: center; justify-content: center;
        z-index: 10000;
        opacity: 0; pointer-events: none; transition: opacity 0.3s;
    }
    #successModal.active { opacity: 1; pointer-events: all; }
    
    .modal-content {
        background: #064e3b; /* Emerald 900 */
        padding: 40px; border-radius: 20px; text-align: center;
        border: 2px solid #10b981;
        box-shadow: 0 0 50px rgba(16, 185, 129, 0.5);
        max-width: 90%;
    }
    .modal-content h2 { font-size: 2rem; font-weight: bold; color: white; margin-bottom: 10px; }
    .modal-content p { font-size: 1.5rem; color: #a7f3d0; margin-bottom: 30px; }
    .btn-next {
        background: white; color: #064e3b; font-size: 1.2rem; font-weight: bold;
        padding: 15px 40px; border-radius: 50px; border: none; cursor: pointer;
        display: inline-flex; align-items: center; gap: 10px;
    }
</style>

<div class="terminal-mode">
    <div class="mb-4 text-center"><h1 class="text-3xl font-bold tracking-widest text-blue-400">SHAHIN GESTÃO</h1><p class="text-sm text-slate-400">TERMINAL DE PONTO</p></div>
    <div id="reader"></div>
    <div class="mt-4"><a href="/logout" class="text-xs text-slate-600 hover:text-slate-400">Sair do Modo Terminal</a></div>
</div>

<!-- Modal de Sucesso -->
<div id="successModal">
    <div class="modal-content">
        <i class="fas fa-check-circle text-6xl text-emerald-400 mb-4"></i>
        <h2 id="modalTitle">REGISTRADO!</h2>
        <p id="modalMsg">Fulano de Tal<br>14:30</p>
        <button class="btn-next" onclick="resetScanner()">
            <i class="fas fa-redo"></i> PRÓXIMO
        </button>
    </div>
</div>

<script>
    const html5QrCode = new Html5Qrcode("reader");
    let isScanning = true;
    
    // Configuração para QR Code denso
    const config = { fps: 10, qrbox: { width: 300, height: 300 } };
    
    html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess, onScanFailure);

    function onScanSuccess(decodedText, decodedResult) {
        if (!isScanning) return;
        isScanning = false;
        
        // Som de Beep
        try { new Audio("https://actions.google.com/sounds/v1/alarms/beep_short.ogg").play(); } catch(e){}

        fetch('/ponto/api/registrar-leitura', { 
            method: 'POST', 
            headers: {'Content-Type': 'application/json'}, 
            body: JSON.stringify({ token: decodedText }) 
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showModal(data.funcionario, data.hora, data.tipo);
            } else {
                alert("ERRO: " + data.error);
                setTimeout(() => { isScanning = true; }, 2000);
            }
        })
        .catch(err => {
            alert("Erro de conexão.");
            setTimeout(() => { isScanning = true; }, 2000);
        });
    }

    function onScanFailure(error) {}

    function showModal(nome, hora, tipo) {
        document.getElementById('modalTitle').innerText = tipo.toUpperCase() + " REGISTRADA";
        document.getElementById('modalMsg').innerHTML = `<strong>${nome}</strong><br>${hora}`;
        document.getElementById('successModal').classList.add('active');
        
        // Auto-fechar em 4s se ninguem clicar
        setTimeout(() => {
            if(document.getElementById('successModal').classList.contains('active')) resetScanner();
        }, 4000);
    }

    function resetScanner() {
        document.getElementById('successModal').classList.remove('active');
        isScanning = true;
    }
</script>
{% endblock %}
"""

# --- 3. SCRIPT FIX MASTER THAYNARA ---
FILE_FIX_MASTER = """
from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    print("--- Corrigindo Usuario Thaynara ---")
    user = User.query.filter_by(username='Thaynara').first()
    
    if user:
        user.role = 'Master'
        user.set_password('1855')
        db.session.commit()
        print(">>> SUCESSO: Thaynara agora é Master com senha '1855'.")
    else:
        # Se nao existir, cria
        novo = User(
            username='Thaynara',
            real_name='Thaynara Master',
            role='Master',
            is_first_access=False,
            cpf='00000000001', # CPF Ficticio Master
            salario=0.0
        )
        novo.set_password('1855')
        db.session.add(novo)
        db.session.commit()
        print(">>> SUCESSO: Usuario Thaynara CRIADO.")
"""

# --- FUNÇÕES ---
def write_file(path, content):
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else '.', exist_ok=True)
    with open(path, 'w', encoding='utf-8') as f: f.write(content.strip())
    print(f"Atualizado: {path}")

def run_fix_master():
    print("Executando fix do usuario Master...")
    try:
        subprocess.run([sys.executable, "fix_master_user.py"], check=True)
    except Exception as e: print(f"Erro fix master: {e}")

def git_update():
    try:
        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        subprocess.run(["git", "push"], check=True)
        print("\n>>> SUCESSO V72! QR PLUS + TERMINAL + MASTER FIX <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass
    try: os.remove("fix_master_user.py")
    except: pass

def main():
    print(f"--- UPDATE V72 QR PLUS: {PROJECT_NAME} ---")
    write_file("app/routes/ponto.py", FILE_BP_PONTO)
    write_file("app/ponto/templates/ponto/registro.html", FILE_PONTO_REGISTRO)
    write_file("app/ponto/templates/ponto/terminal_leitura.html", FILE_TERMINAL_HTML)
    write_file("fix_master_user.py", FILE_FIX_MASTER)
    
    run_fix_master()
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


