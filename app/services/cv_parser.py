import os
import json
import re
import PyPDF2
from PIL import Image
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def analisar_curriculo_ia(file_storage):
    """
    Recebe um ficheiro (PDF ou Imagem), processa o conteúdo e pede à I.A. 
    para estruturar os dados do candidato (Nome, Email, Telefone, Tags).
    """
    try:
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente.")
            return None
            
        genai.configure(api_key=api_key)
        # O modelo Flash é incrivelmente rápido e tem visão nativa
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        prompt = """
        Você é um assistente de Recursos Humanos especialista em ATS.
        Analise o currículo em anexo (pode ser texto ou uma imagem do documento) 
        e extraia as seguintes informações no formato JSON estrito:
        
        {
            "nome": "Nome completo do candidato",
            "email": "Email do candidato (ou null se não encontrar)",
            "telefone": "Telefone com DDD (ou null se não encontrar)",
            "palavras_chave": "Uma lista com as 5 principais habilidades técnicas ou qualificações do candidato separadas por vírgula (ex: Excel, CNH B, Liderança, Empilhador). Seja muito breve."
        }
        """
        
        # Prepara a lista de conteúdos que vamos enviar para a I.A.
        conteudo_para_ia = [prompt]
        filename = file_storage.filename.lower()
        
        # 1. Se for PDF (Extrai o texto)
        if filename.endswith('.pdf'):
            reader = PyPDF2.PdfReader(file_storage)
            texto_cv = ""
            for i in range(min(len(reader.pages), 3)):
                texto_cv += reader.pages[i].extract_text() + "\n"
                
            if not texto_cv.strip():
                return None
            conteudo_para_ia.append(f"Currículo:\n{texto_cv[:10000]}")
            
        # 2. Se for Imagem (Abre a foto para a I.A. ver)
        elif filename.endswith(('.jpg', '.jpeg', '.png')):
            imagem = Image.open(file_storage)
            conteudo_para_ia.append(imagem)
            
        else:
            logger.warning(f"Formato de ficheiro não suportado pela I.A.: {filename}")
            return None

        # IMPORTANTE: Reseta o ponteiro do arquivo para que o GCP Storage consiga salvá-lo depois!
        file_storage.seek(0)
        
        # Envia tudo para o Gemini
        response = model.generate_content(conteudo_para_ia)
        resposta_texto = response.text
        
        # Limpa o texto para garantir que pegamos apenas o JSON gerado
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        if json_match:
            dados_extraidos = json.loads(json_match.group(0))
            return dados_extraidos
            
        return None

    except Exception as e:
        logger.error(f"Erro ao analisar CV com I.A.: {e}")
        file_storage.seek(0) 
        return None

