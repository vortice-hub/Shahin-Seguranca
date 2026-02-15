import os
import shutil
import subprocess
import sys

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V69: Fix Critical - Restaurando Scanner e Corrigindo Variavel Hoje no Registro"

# --- 1. APP/ROUTES/PONTO.PY (COMPLETO: API + SCANNER + REGISTRO + ESPELHO) ---
FILE_BP_PONTO = """
from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from app import db
from app.models import PontoRegistro, PontoResumo, User, PontoAjuste
from app.utils import get_brasil_time, calcular_dia, format_minutes_to_hm, data_por_extenso
from datetime import datetime, date
from sqlalchemy import func
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature

ponto_bp = Blueprint('ponto', __name__, url_prefix='/ponto')

# --- 1. API QR CODE (BACKEND) ---
@ponto_bp.route('/api/gerar-token', methods=['GET'])
@login_required
def gerar_token_qrcode():
    if current_user.role == 'Terminal': return jsonify({'error': 'Terminal não gera token'}), 403
    s = URLSafeTimedSerializer(current_app.secret_key)
    token = s.dumps({'user_id': current_user.id, 'timestamp': get_brasil_time().timestamp()})
    return jsonify({'token': token})

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
        pontos_hoje = PontoRegistro.query.filter_by(user_id=user_alvo.id, data_registro=hoje).order_by(PontoRegistro.hora_registro).all()
        
        proxima = "Entrada"
        if len(pontos_hoje) == 1: proxima = "Ida Almoço"
        elif len(pontos_hoje) == 2: proxima = "Volta Almoço"
        elif len(pontos_hoje) == 3: proxima = "Saída"
        elif len(pontos_hoje) >= 4: proxima = "Extra"
        
        novo = PontoRegistro(user_id=user_alvo.id, data_registro=hoje, hora_registro=get_brasil_time().time(), tipo=proxima, latitude='QR-Code', longitude='Presencial')
        db.session.add(novo); db.session.commit(); calcular_dia(user_alvo.id, hoje)
        
        return jsonify({'success': True, 'message': f'Ponto registrado: {proxima}', 'funcionario': user_alvo.real_name, 'hora': novo.hora_registro.strftime('%H:%M')})
    except SignatureExpired: return jsonify({'error': 'QR Code expirado.'}), 400
    except BadSignature: return jsonify({'error': 'QR Code inválido.'}), 400
    except Exception as e: return jsonify({'error': f'Erro interno: {str(e)}'}), 500

# --- 2. ROTA SCANNER (VISUAL TERMINAL) ---
@ponto_bp.route('/scanner')
@login_required
def terminal_scanner():
    # Rota exclusiva para o Terminal ler os códigos
    if current_user.role != 'Terminal' and current_user.role != 'Master':
        flash('Acesso restrito ao Terminal de Ponto.')
        return redirect(url_for('main.dashboard'))
    # Garante que o template existe (vamos recriar no script se precisar)
    return render_template('ponto/terminal_leitura.html')

# --- 3. REGISTRO MANUAL/QR CODE (FUNCIONARIO) ---
@ponto_bp.route('/registrar', methods=['GET', 'POST'])
@login_required
def registrar_ponto():
    # Se o usuario Terminal tentar acessar o registro manual, joga ele pro scanner
    if current_user.role == 'Terminal':
        return redirect(url_for('ponto.terminal_scanner'))

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
    
    # CORREÇÃO CRÍTICA: Passando 'hoje' explicitamente
    return render_template('ponto/registro.html', proxima_acao=prox, hoje_extenso=hoje_extenso, pontos=pontos, bloqueado=bloqueado, motivo=motivo, hoje=hoje)

# --- 4. ESPELHO DE PONTO ---
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

# --- 5. SOLICITAR AJUSTE ---
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

# --- 2. TEMPLATE DO TERMINAL (Restaurando caso tenha sumido) ---
FILE_TERMINAL_HTML = """
{% extends 'base.html' %}
{% block content %}
<script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>
<style>
    .terminal-mode { position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: #0f172a; z-index: 9999; display: flex; flex-direction: column; align-items: center; justify-content: center; color: white; }
    #reader { width: 100%; max-width: 500px; border-radius: 20px; overflow: hidden; border: 4px solid #3b82f6; background: black; }
    .status-box { margin-top: 20px; padding: 20px; border-radius: 15px; width: 90%; max-width: 500px; text-align: center; background: #1e293b; border: 1px solid #334155; transition: all 0.3s ease; }
    .status-success { background: #064e3b; border-color: #10b981; }
    .status-error { background: #7f1d1d; border-color: #ef4444; }
    .last-scans { margin-top: 20px; width: 90%; max-width: 500px; height: 150px; overflow-y: auto; background: rgba(255,255,255,0.05); border-radius: 10px; padding: 10px; }
    .scan-item { font-size: 0.8rem; padding: 8px; border-bottom: 1px solid rgba(255,255,255,0.1); display: flex; justify-content: space-between; }
</style>
<div class="terminal-mode">
    <div class="mb-4 text-center"><h1 class="text-2xl font-bold tracking-widest text-blue-400">SHAHIN GESTÃO</h1><p class="text-xs text-slate-400">TERMINAL DE PONTO</p></div>
    <div id="reader"></div>
    <div id="statusBox" class="status-box"><h2 id="statusTitle" class="text-xl font-bold">Aguardando...</h2><p id="statusMsg" class="text-sm text-slate-400">Aproxime o QR Code do celular</p></div>
    <div class="last-scans" id="historyLog"></div>
    <div class="mt-4"><a href="/logout" class="text-xs text-slate-600 hover:text-slate-400">Sair do Modo Terminal</a></div>
</div>
<script>
    const html5QrCode = new Html5Qrcode("reader");
    let isScanning = true;
    const config = { fps: 10, qrbox: { width: 250, height: 250 } };
    html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess, onScanFailure);
    function onScanSuccess(decodedText, decodedResult) {
        if (!isScanning) return;
        isScanning = false;
        processarPonto(decodedText);
        setTimeout(() => { isScanning = true; }, 3000);
    }
    function onScanFailure(error) {}
    function processarPonto(token) {
        const box = document.getElementById('statusBox');
        const title = document.getElementById('statusTitle');
        const msg = document.getElementById('statusMsg');
        box.className = "status-box"; title.innerText = "Processando...";
        fetch('/ponto/api/registrar-leitura', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ token: token }) })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                box.classList.add('status-success'); title.innerText = "REGISTRADO!"; msg.innerText = `${data.funcionario} às ${data.hora}`; addToHistory(data.funcionario, data.hora, "ok");
            } else {
                box.classList.add('status-error'); title.innerText = "NÃO REGISTRADO"; msg.innerText = data.error;
            }
        })
        .catch(err => { box.classList.add('status-error'); title.innerText = "ERRO DE REDE"; msg.innerText = "Verifique a conexão."; })
        .finally(() => { setTimeout(() => { box.className = "status-box"; title.innerText = "Aguardando..."; msg.innerText = "Aproxime o QR Code"; }, 2500); });
    }
    function addToHistory(nome, hora, status) {
        const log = document.getElementById('historyLog');
        const item = document.createElement('div');
        item.className = "scan-item";
        item.innerHTML = `<span class="text-emerald-400">${nome}</span> <span>${hora}</span>`;
        log.prepend(item);
    }
</script>
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
        print("\n>>> SUCESSO V69! PONTO E SCANNER CORRIGIDOS <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V69 PONTO CONSOLIDATION: {PROJECT_NAME} ---")
    write_file("app/routes/ponto.py", FILE_BP_PONTO)
    write_file("app/ponto/templates/ponto/terminal_leitura.html", FILE_TERMINAL_HTML)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


