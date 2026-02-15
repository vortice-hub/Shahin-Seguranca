import os
import sys
import subprocess

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Shahin Gestão"
COMMIT_MSG = "V65: Fix Critical - Adicionando tokens CSRF nos formularios de autenticacao"

# --- 1. LOGIN (COM TOKEN) ---
FILE_LOGIN = """
{% extends 'base.html' %}
{% block content %}
<div class="flex flex-col items-center justify-center min-h-[60vh]">
    <div class="w-16 h-16 bg-blue-600 rounded-2xl flex items-center justify-center text-white font-bold text-3xl mb-6 shadow-lg shadow-blue-200">S</div>
    <div class="bg-white p-8 rounded-2xl shadow-xl border border-slate-100 w-full max-w-sm">
        <h2 class="text-xl font-bold text-center text-slate-800 mb-6">Acesso Shahin</h2>
        <form action="/login" method="POST" class="space-y-4">
            <!-- TOKEN DE SEGURANÇA OBRIGATÓRIO -->
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
            
            <div><label class="block text-xs font-bold text-slate-400 uppercase mb-2">Usuário</label><input type="text" name="username" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500" placeholder="ex: joao.silva" required></div>
            <div><label class="block text-xs font-bold text-slate-400 uppercase mb-2">Senha</label><input type="password" name="password" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-blue-500" placeholder="••••••" required></div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-lg transition">ENTRAR</button>
        </form>
    </div>
    
    <a href="/cadastrar" class="mt-6 text-sm text-blue-600 font-bold hover:underline">
        Sou Funcionário e quero criar minha senha
    </a>
    
    <p class="text-xs text-slate-400 mt-6">&copy; 2026 Vortice Company</p>
</div>
{% endblock %}
"""

# --- 2. AUTO CADASTRO (COM TOKEN NAS DUAS ETAPAS) ---
FILE_AUTO_CADASTRO = """
{% extends 'base.html' %}
{% block content %}
<div class="flex flex-col items-center justify-center min-h-[60vh]">
    <div class="bg-white p-8 rounded-2xl shadow-xl border border-slate-100 w-full max-w-md">
        
        <!-- ETAPA 1: DIGITAR CPF -->
        {% if step == 1 %}
        <h2 class="text-xl font-bold text-slate-800 mb-2">Primeiro Acesso</h2>
        <p class="text-sm text-slate-500 mb-6">Digite seu CPF para localizar seu cadastro.</p>
        <form action="/cadastrar" method="POST" class="space-y-4">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
            <input type="hidden" name="step" value="1">
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">CPF (Somente Números)</label>
                <input type="text" name="cpf" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 font-bold text-lg tracking-wide focus:outline-none focus:border-blue-500" placeholder="000.000.000-00" required>
            </div>
            <button type="submit" class="w-full bg-blue-600 hover:bg-blue-700 text-white font-bold py-4 rounded-lg shadow-lg transition">CONTINUAR</button>
        </form>
        {% endif %}

        <!-- ETAPA 2: CRIAR SENHA -->
        {% if step == 2 %}
        <h2 class="text-xl font-bold text-emerald-700 mb-2">Bem-vindo(a), {{ nome }}!</h2>
        <p class="text-sm text-slate-500 mb-6">Confirme seus dados e crie uma senha segura.</p>
        <form action="/cadastrar" method="POST" class="space-y-4">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
            <input type="hidden" name="step" value="2">
            <input type="hidden" name="cpf" value="{{ cpf }}">
            
            <div class="bg-slate-50 p-4 rounded-lg border border-slate-100 mb-4">
                <p class="text-xs text-slate-400 font-bold uppercase">CPF</p>
                <p class="font-mono text-slate-800 font-bold">{{ cpf }}</p>
            </div>

            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Crie sua Senha</label>
                <input type="password" name="password" class="w-full bg-white border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-emerald-500" placeholder="Mínimo 6 caracteres" required>
            </div>
            
            <button type="submit" class="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-bold py-4 rounded-lg shadow-lg transition">FINALIZAR CADASTRO</button>
        </form>
        {% endif %}

        <div class="text-center mt-4">
            <a href="/login" class="text-xs text-slate-400 hover:text-slate-600">Voltar para Login</a>
        </div>
    </div>
</div>
{% endblock %}
"""

# --- 3. PRIMEIRO ACESSO (TROCA DE SENHA) ---
FILE_PRIMEIRO_ACESSO = """
{% extends 'base.html' %}
{% block content %}
<div class="flex flex-col items-center justify-center min-h-[60vh]">
    <div class="bg-white p-8 rounded-2xl shadow-xl border-l-4 border-yellow-400 w-full max-w-sm">
        <h2 class="text-xl font-bold text-slate-800 mb-2">Primeiro Acesso</h2>
        <p class="text-sm text-slate-500 mb-6">Por segurança, você deve definir uma nova senha pessoal.</p>
        <form action="/primeiro-acesso" method="POST" class="space-y-4">
            <input type="hidden" name="csrf_token" value="{{ csrf_token() }}"/>
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Nova Senha</label>
                <input type="password" name="nova_senha" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-yellow-500" required>
            </div>
            <div>
                <label class="block text-xs font-bold text-slate-400 uppercase mb-2">Confirmar Senha</label>
                <input type="password" name="confirmacao" class="w-full bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 focus:outline-none focus:border-yellow-500" required>
            </div>
            <button type="submit" class="w-full bg-yellow-500 hover:bg-yellow-600 text-white font-bold py-4 rounded-lg shadow-lg transition">SALVAR E ACESSAR</button>
        </form>
    </div>
</div>
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
        print("\n>>> SUCESSO V65! SEGURANÇA CSRF CORRIGIDA <<<")
    except Exception as e: print(f"Git: {e}")

def self_destruct():
    try: os.remove(os.path.abspath(__file__))
    except: pass

def main():
    print(f"--- UPDATE V65 CSRF FIX: {PROJECT_NAME} ---")
    write_file("app/auth/templates/auth/login.html", FILE_LOGIN)
    write_file("app/auth/templates/auth/auto_cadastro.html", FILE_AUTO_CADASTRO)
    write_file("app/auth/templates/auth/primeiro_acesso.html", FILE_PRIMEIRO_ACESSO)
    git_update()
    self_destruct()

if __name__ == "__main__":
    main()


