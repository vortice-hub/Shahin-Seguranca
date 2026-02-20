import os
import zipfile
import glob
import shutil

def restaurar_backup_recente():
    pasta_backups = 'backups'
    diretorio_projeto = '.' # Raiz do projeto

    # 1. Localiza todos os arquivos .zip na pasta de backups
    arquivos_zip = glob.glob(os.path.join(pasta_backups, '*.zip'))

    if not arquivos_zip:
        print(f"❌ Erro: Nenhum arquivo .zip encontrado na pasta '{pasta_backups}'.")
        return

    # 2. Encontra o arquivo mais recente baseado na data de modificação
    backup_recente = max(arquivos_zip, key=os.path.getmtime)
    print(f"📦 Backup identificado: {backup_recente}")

    try:
        # 3. Descompacta o backup
        print(f"⏳ Restaurando arquivos... isso pode substituir arquivos existentes.")
        with zipfile.ZipFile(backup_recente, 'r') as zip_ref:
            # Extrai tudo para a raiz do projeto
            zip_ref.extractall(diretorio_projeto)
        
        print(f"✅ Sucesso! O projeto foi restaurado para a versão de: {backup_recente}")
        print("🚀 Agora você pode rodar o comando de deploy novamente.")

    except Exception as e:
        print(f"❌ Ocorreu um erro durante a restauração: {e}")

if __name__ == "__main__":
    restaurar_backup_recente()

