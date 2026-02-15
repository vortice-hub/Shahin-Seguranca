import os
from datetime import datetime

# --- CONFIGURAÇÕES ---
OUTPUT_FILE = "PROJECT_FULL_CONTEXT.txt"

# Pastas para ignorar (Adicionei as solicitadas e padroes de sistema)
IGNORE_DIRS = {
    '.git', '__pycache__', '.venv', 'venv', 'env', 'node_modules', 
    'backup', 'backups', 'backups_auto', 'app_backup_20260214_220800',
    '.idea', '.vscode'
}

IGNORE_FILES = {
    '.DS_Store', 'Thumbs.db', OUTPUT_FILE, 
    'generate_project_snapshot.py', 'generate_snapshot_v2.py',
    'db.sqlite3' # Ignora banco local se houver
}

# Extensões que queremos ler o conteúdo
READ_EXTENSIONS = {'.py', '.html', '.txt', '.md', '.css', '.js', '.json', '.xml'}
# Arquivos específicos sem extensão que queremos ler
READ_FILES = {'Procfile', 'requirements.txt', 'runtime.txt', 'Dockerfile', '.env.example'}

def should_ignore_dir(dirname):
    """Verifica se o diretorio deve ser ignorado."""
    if dirname in IGNORE_DIRS:
        return True
    # Ignora qualquer pasta que comece com app_backup_ (para backups futuros)
    if dirname.startswith('app_backup_'):
        return True
    return False

def generate_tree(startpath, prefix=""):
    """Gera a estrutura de árvore visual."""
    tree_str = ""
    files = []
    dirs = []

    try:
        for item in os.listdir(startpath):
            path = os.path.join(startpath, item)
            if os.path.isdir(path):
                if not should_ignore_dir(item):
                    dirs.append(item)
            else:
                if item not in IGNORE_FILES:
                    files.append(item)
    except PermissionError:
        return ""

    dirs.sort()
    files.sort()

    entries = dirs + files
    
    for i, entry in enumerate(entries):
        is_last = (i == len(entries) - 1)
        connector = "└── " if is_last else "├── "
        
        if entry in dirs:
            tree_str += f"{prefix}{connector}{entry}/\n"
            extension = "    " if is_last else "│   "
            tree_str += generate_tree(os.path.join(startpath, entry), prefix + extension)
        else:
            tree_str += f"{prefix}{connector}{entry}\n"

    return tree_str

def get_file_content(filepath):
    """Lê o conteúdo do arquivo com segurança."""
    ext = os.path.splitext(filepath)[1]
    filename = os.path.basename(filepath)
    
    if ext in READ_EXTENSIONS or filename in READ_FILES:
        try:
            with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                content = f.read()
                return content
        except Exception as e:
            return f"[Erro ao ler arquivo: {e}]"
    return "[Conteúdo binário ou não listado para leitura]"

def main():
    root_dir = os.getcwd()
    
    print(f"--- GERANDO SNAPSHOT DO PROJETO ---")
    print(f"Raiz: {root_dir}")
    print(f"Ignorando pastas de backup...")
    
    with open(OUTPUT_FILE, 'w', encoding='utf-8') as out:
        # 1. Cabeçalho
        out.write("="*50 + "\n")
        out.write(f"SNAPSHOT DO PROJETO: Shahin Gestão\n")
        out.write(f"Gerado em: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        out.write("="*50 + "\n\n")
        
        # 2. Estrutura de Pastas (Tree)
        out.write("--- ESTRUTURA DE ARQUIVOS ---\n")
        out.write(".\n")
        out.write(generate_tree(root_dir))
        out.write("\n" + "="*50 + "\n\n")
        
        # 3. Conteúdo dos Arquivos
        out.write("--- CONTEÚDO DOS ARQUIVOS ---\n\n")
        
        for root, dirs, files in os.walk(root_dir):
            # Modifica a lista dirs "in-place" para impedir o os.walk de entrar nas pastas ignoradas
            dirs[:] = [d for d in dirs if not should_ignore_dir(d)]
            
            # Ordena para ficar bonito
            dirs.sort()
            files.sort()
            
            for file in files:
                if file in IGNORE_FILES: continue
                
                filepath = os.path.join(root, file)
                relative_path = os.path.relpath(filepath, root_dir)
                
                # Verifica se deve ler
                ext = os.path.splitext(file)[1]
                if ext in READ_EXTENSIONS or file in READ_FILES:
                    print(f"Lendo: {relative_path}")
                    content = get_file_content(filepath)
                    
                    out.write(f"FILE: {relative_path}\n")
                    out.write("-" * len(f"FILE: {relative_path}") + "\n")
                    out.write(content + "\n")
                    out.write("\n" + "#"*50 + "\n\n")

    print(f"\nCONCLUÍDO! Arquivo gerado: {OUTPUT_FILE}")

if __name__ == "__main__":
    main()


