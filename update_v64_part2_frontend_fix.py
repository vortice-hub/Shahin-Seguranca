import os
import sys
import subprocess # Adicionado a importação que faltava

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V64 Part 2: Frontend QR Code - Tela de Cracha Digital Dinamico"

# --- 1. ATUALIZAR TEMPLATE REGISTRO.HTML (Substituir botões por QR Code) ---
FILE_PONTO_REGISTRO = """
{% extends 'base.html' %}
{% block content %}
<!-- Biblioteca QR Code (Leve e rapida via CDN) -->
<script src="https://cdnjs.cloudflare.com/ajax/libs/qrcodejs/1.0.0/qrcode.min.js"></script>

<div class="max-w-md mx-auto text-center">
    
    <!-- Cabeçalho -->
    <div class="mb-6">
        <h2 class="text-2xl font-bold text-slate-800">Meu Ponto</h2>
        <p class="text-sm text-slate-500">Aproxime este código do Terminal na portaria.</p>
    </div>

    {% if bloqueado %}
    <!-- Bloqueio de Escala (Mantido da V26) -->
    <div class="bg-red-50 border-l-4 border-red-500 p-6 rounded-r-xl shadow-md text-left mb-8">
        <h3 class="text-lg font-bold text-red-700 flex items-center gap-2"><i class="fas fa-ban"></i> ACESSO NEGADO</h3>
        <p class="text-sm text-red-600 mt-2">{{ motivo }}</p>
    </div>
    {% else %}
    
    <!-- Área do QR Code -->
    <div class="bg-white rounded-3xl shadow-xl border border-slate-200 p-8 relative overflow-hidden">
        
        <!-- Faixa Decorativa -->
        <div class="absolute top-0 left-0 w-full h-2 bg-gradient-to-r from-blue-500 to-purple-600"></div>

        <!-- Dados do Usuário -->
        <div class="mb-6">
            <h3 class="text-xl font-bold text-slate-800">{{ current_user.real_name }}</h3>
            <p class="text-xs text-slate-400 font-mono uppercase">{{ current_user.role }}</p>
        </div>

        <!-- O QR Code (Container) -->
        <div class="flex justify-center mb-6">
            <div id="qrcode" class="p-2 border-4 border-slate-100 rounded-xl"></div>
        </div>

        <!-- Barra de Tempo de Vida -->
        <div class="w-full bg-slate-100 rounded-full h-2.5 mb-2">
            <div id="progressBar" class="bg-blue-600 h-2.5 rounded-full transition-all duration-1000 ease-linear" style="width: 100%"></div>
        </div>
        <p class="text-xs text-slate-400 font-mono" id="statusToken">Atualizando em <span id="countdown">30</span>s...</p>

        <!-- Status do Dia -->
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

    <!-- Histórico Rápido -->
    <div class="mt-8 text-left">
        <h3 class="text-xs font-bold text-slate-400 uppercase mb-3 ml-1">Batidas de Hoje</h3>
        <div class="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden divide-y divide-slate-100">
            {% for p in pontos %}
            <div class="px-4 py-3 flex justify-between items-center">
                <span class="text-sm font-bold text-slate-700 flex items-center gap-2">
                    <i class="fas fa-circle text-[6px] {% if 'Entrada' in p.tipo %}text-emerald-500{% else %}text-amber-500{% endif %}"></i>
                    {{ p.tipo }}
                </span>
                <span class="text-sm font-mono text-slate-500 font-bold bg-slate-50 px-2 py-1 rounded">
                    {{ p.hora_registro.strftime('%H:%M') }}
                </span>
            </div>
            {% else %}
            <div class="p-6 text-center text-xs text-slate-400">
                <i class="far fa-clock text-xl mb-2 opacity-30 block"></i>
                Ainda não iniciou a jornada.
            </div>
            {% endfor %}
        </div>
    </div>
</div>

<script>
    let timerInterval;
    const TIME_LIMIT = 30; // Segundos de validade
    let timeLeft = TIME_LIMIT;

    function generateQRCode() {
        // 1. Pede um novo token seguro para o servidor
        fetch('/ponto/api/gerar-token')
            .then(response => response.json())
            .then(data => {
                if (data.error) {
                    document.getElementById('qrcode').innerHTML = `<p class="text-red-500 text-xs">${data.error}</p>`;
                    return;
                }

                // 2. Limpa o QR anterior
                const container = document.getElementById("qrcode");
                container.innerHTML = "";

                // 3. Desenha o novo
                new QRCode(container, {
                    text: data.token,
                    width: 180,
                    height: 180,
                    colorDark : "#1e293b",
                    colorLight : "#ffffff",
                    correctLevel : QRCode.CorrectLevel.M
                });

                // 4. Reinicia o contador visual
                resetTimer();
            })
            .catch(err => {
                console.error("Erro ao gerar token:", err);
                document.getElementById("statusToken").innerText = "Erro de conexão. Tentando...";
            });
    }

    function resetTimer() {
        timeLeft = TIME_LIMIT;
        clearInterval(timerInterval);
        
        const bar = document.getElementById("progressBar");
        const text = document.getElementById("countdown");

        timerInterval = setInterval(() => {
            timeLeft--;
            text.innerText = timeLeft;
            
            // Calcula porcentagem
            const pct = (timeLeft / TIME_LIMIT) * 100;
            bar.style.width = pct + "%";

            // Muda cor se estiver acabando
            if (timeLeft < 5) {
                bar.classList.remove('bg-blue-600');
                bar.classList.add('bg-red-500');
            } else {
                bar.classList.add('bg-blue-600');
                bar.classList.remove('bg-red-500');
            }

            if (timeLeft <= 0) {
                generateQRCode(); // Gera novo automaticamente
            }
        }, 1000);
    }

    // Inicia ao carregar
    document.addEventListener("DOMContentLoaded", () => {
        {% if not bloqueado %}
            generateQRCode();
        {% endif %}
    });
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
        print("\n>>> SUCESSO V64 PARTE 2! FRONTEND DO CRACHÁ ATIVO <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V64 PARTE 2 FIX (FRONTEND): {PROJECT_NAME} ---")
    write_file("app/ponto/templates/ponto/registro.html", FILE_PONTO_REGISTRO)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


