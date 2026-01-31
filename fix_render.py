import os
import shutil
import subprocess
import sys
from datetime import datetime

# --- CONFIGURAÇÕES ---
PROJECT_NAME = "Thay RH"
COMMIT_MSG = "Fix: Forcar Procfile e Dependencias para Render"

# --- CONTEÚDO CORRIGIDO ---

# Garante que gunicorn está aqui
FILE_REQ = """flask
flask-sqlalchemy
psycopg2-binary
gunicorn
"""

# O comando exato que o Render precisa
FILE_PROCFILE = """web: gunicorn app:app"""

# --- FUNÇÕES ---

def create_backup():
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = os.path.join("backup", timestamp)
    # Faz backup apenas dos arquivos de configuracao criticos desta vez
    files_to_check = ["requirements.txt", "Procfile"]
    
    for file_path in files_to_check:
        if os.path.exists(file_path):
            dest = os.path.join(backup_dir, file_path)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(file_path, dest)
    print(f"Backup de config salvo em: {backup_dir}")

def write_file(path, content):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(content.strip())
    print(f"Arquivo recriado: {path}")

def git_force_update():
    try:
        print("Adicionando arquivos...")
        subprocess.run(["git", "add", "."], check=True)
        
        print("Commitando correcao...")
        subprocess.run(["git", "commit", "-m", COMMIT_MSG], check=False)
        
        print("Enviando para o GitHub...")
        subprocess.run(["git", "push"], check=True)
        print("\n>>> Push realizado com sucesso! <<<")
    except subprocess.CalledProcessError as e:
        print(f"Erro no Git: {e}")

def self_destruct():
    try:
        os.remove(os.path.abspath(__file__))
    except:
        pass

def main():
    print(f"--- CORREÇÃO DE DEPLOY: {PROJECT_NAME} ---")
    
    create_backup()
    
    # Reescreve arquivos vitais para o Render
    write_file("requirements.txt", FILE_REQ)
    write_file("Procfile", FILE_PROCFILE)
    
    git_force_update()
    
    print("\n" + "="*50)
    print("ATENÇÃO - AÇÃO MANUAL PODE SER NECESSÁRIA NO RENDER")
    print("="*50)
    print("Se o erro 'ModuleNotFoundError' persistir após este deploy,")
    print("faça o seguinte:")
    print("1. Acesse o painel do seu projeto no Render.com")
    print("2. Vá em 'Settings' (Configurações)")
    print("3. Procure o campo 'Start Command'")
    print("4. Se estiver escrito 'gunicorn your_application.wsgi', APAGUE ou MUDE para:")
    print("   gunicorn app:app")
    print("="*50 + "\n")
    
    self_destruct()

if __name__ == "__main__":
    main()


