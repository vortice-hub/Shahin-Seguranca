import os
import sys
import subprocess

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V64 Part 3: Terminal de Leitura - Scanner QR Code Ativo"

# --- 1. CRIAR TEMPLATE DO TERMINAL (QUIOSQUE) ---
FILE_TERMINAL_HTML = """
{% extends 'base.html' %}
{% block content %}
<!-- Biblioteca de Leitura QR Code -->
<script src="https://unpkg.com/html5-qrcode" type="text/javascript"></script>

<style>
    /* Estilo "Modo Quiosque" - Esconde menu lateral se possível ou foca na leitura */
    .terminal-mode {
        position: fixed;
        top: 0; left: 0; width: 100%; height: 100%;
        background: #0f172a; /* Slate 900 */
        z-index: 9999;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: white;
    }
    #reader {
        width: 100%;
        max-width: 500px;
        border-radius: 20px;
        overflow: hidden;
        border: 4px solid #3b82f6;
        background: black;
    }
    .status-box {
        margin-top: 20px;
        padding: 20px;
        border-radius: 15px;
        width: 90%;
        max-width: 500px;
        text-align: center;
        background: #1e293b;
        border: 1px solid #334155;
        transition: all 0.3s ease;
    }
    .status-success { background: #064e3b; border-color: #10b981; }
    .status-error { background: #7f1d1d; border-color: #ef4444; }
    
    .last-scans {
        margin-top: 20px;
        width: 90%;
        max-width: 500px;
        height: 150px;
        overflow-y: auto;
        background: rgba(255,255,255,0.05);
        border-radius: 10px;
        padding: 10px;
    }
    .scan-item {
        font-size: 0.8rem;
        padding: 8px;
        border-bottom: 1px solid rgba(255,255,255,0.1);
        display: flex;
        justify-content: space-between;
    }
</style>

<div class="terminal-mode">
    <div class="mb-4 text-center">
        <h1 class="text-2xl font-bold tracking-widest text-blue-400">SHAHIN GESTÃO</h1>
        <p class="text-xs text-slate-400">TERMINAL DE PONTO</p>
    </div>

    <!-- Área da Câmera -->
    <div id="reader"></div>

    <!-- Área de Status (Feedback) -->
    <div id="statusBox" class="status-box">
        <h2 id="statusTitle" class="text-xl font-bold">Aguardando...</h2>
        <p id="statusMsg" class="text-sm text-slate-400">Aproxime o QR Code do celular</p>
    </div>

    <!-- Lista de Últimos Registros -->
    <div class="last-scans" id="historyLog">
        <!-- Itens injetados via JS -->
    </div>
    
    <div class="mt-4">
        <a href="/logout" class="text-xs text-slate-600 hover:text-slate-400">Sair do Modo Terminal</a>
    </div>
</div>

<!-- Som de Beep (Base64 curto para não depender de arquivo externo) -->
<audio id="beepSound" src="data:audio/wav;base64,UklGRl9vT19XQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YU"></audio>

<script>
    const html5QrCode = new Html5Qrcode("reader");
    let isScanning = true;

    // Configuração do Scanner
    const config = { fps: 10, qrbox: { width: 250, height: 250 } };
    
    // Inicia Câmera (Traseira por padrão)
    html5QrCode.start({ facingMode: "environment" }, config, onScanSuccess, onScanFailure);

    function onScanSuccess(decodedText, decodedResult) {
        if (!isScanning) return; // Evita leitura dupla rapida
        
        isScanning = False; // Pausa leitura
        processarPonto(decodedText);
        
        // Bloqueia nova leitura por 3 segundos para dar tempo de feedback
        setTimeout(() => { isScanning = true; }, 3000);
    }

    function onScanFailure(error) {
        // Console log é muito verboso, ignorar erros de "não encontrou qr code neste frame"
    }

    function processarPonto(token) {
        const box = document.getElementById('statusBox');
        const title = document.getElementById('statusTitle');
        const msg = document.getElementById('statusMsg');
        
        box.className = "status-box"; // Reset cor
        title.innerText = "Processando...";
        
        // Envia para API
        fetch('/ponto/api/registrar-leitura', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ token: token })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // Sucesso
                playBeep();
                box.classList.add('status-success');
                title.innerText = "REGISTRADO!";
                msg.innerText = `${data.funcionario} às ${data.hora}`;
                addToHistory(data.funcionario, data.hora, "ok");
            } else {
                // Erro (Vencido ou Inválido)
                box.classList.add('status-error');
                title.innerText = "NÃO REGISTRADO";
                msg.innerText = data.error;
            }
        })
        .catch(err => {
            box.classList.add('status-error');
            title.innerText = "ERRO DE REDE";
            msg.innerText = "Verifique a conexão.";
        })
        .finally(() => {
            // Volta ao normal após 2.5s
            setTimeout(() => {
                box.className = "status-box";
                title.innerText = "Aguardando...";
                msg.innerText = "Aproxime o QR Code";
            }, 2500);
        });
    }

    function addToHistory(nome, hora, status) {
        const log = document.getElementById('historyLog');
        const item = document.createElement('div');
        item.className = "scan-item";
        item.innerHTML = `<span class="text-emerald-400">${nome}</span> <span>${hora}</span>`;
        log.prepend(item); // Adiciona no topo
    }

    function playBeep() {
        // Tenta tocar um som simples
        try {
            const context = new (window.AudioContext || window.webkitAudioContext)();
            const osc = context.createOscillator();
            osc.type = "sine";
            osc.frequency.value = 880;
            osc.connect(context.destination);
            osc.start();
            osc.stop(context.currentTime + 0.1);
        } catch(e) {}
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
        print("\n>>> SUCESSO V64 PARTE 3! TERMINAL PRONTO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V64 PARTE 3 (FINAL): {PROJECT_NAME} ---")
    write_file("app/ponto/templates/ponto/terminal_leitura.html", FILE_TERMINAL_HTML)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


