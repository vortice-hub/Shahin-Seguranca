import os
import zipfile
from datetime import datetime

def create_backup():
    # 1. Configurações
    project_root = os.getcwd()
    backup_folder = os.path.join(project_root, 'backups')
    
    # Pastas e arquivos que NÃO queremos no backup
    ignore_dirs = {'.git', '__pycache__', 'venv', '.venv', 'env', 'backups', 'node_modules', '.idea', '.vscode', 'uploads', 'instance'}
    ignore_files = {'.DS_Store', 'backup.py', '.env'} # Ignorando senhas (.env)
    ignore_extensions = {'.log', '.pyc', '.sqlite3', '.db'} # Ignora logs e bancos locais para evitar corrupção

    # 2. Garante que a pasta de backups existe
    if not os.path.exists(backup_folder):
        os.makedirs(backup_folder)
        print(f"📁 Pasta '{backup_folder}' criada com sucesso.")

    # 3. Define o nome do arquivo com Timestamp
    timestamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    zip_filename = f"backup_shahin_codigo_{timestamp}.zip"
    zip_path = os.path.join(backup_folder, zip_filename)

    print(f"⏳ Iniciando backup do código: {zip_filename}...")

    # 4. Processo de Zipagem
    try:
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
            for root, dirs, files in os.walk(project_root):
                # Remove pastas ignoradas da lista para não entrar nelas
                dirs[:] = [d for d in dirs if d not in ignore_dirs]
                
                for file in files:
                    # Ignora arquivos específicos
                    if file in ignore_files:
                        continue
                    
                    # Ignora extensões específicas
                    if any(file.endswith(ext) for ext in ignore_extensions):
                        continue
                    
                    # Caminho completo do arquivo
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, project_root)
                    
                    zipf.write(file_path, arcname)
        
        print(f"✅ Backup de código concluído com sucesso!")
        print(f"📍 Local: {zip_path}")
        
    except Exception as e:
        print(f"❌ Erro ao criar backup: {e}")

if __name__ == "__main__":
    create_backup()

