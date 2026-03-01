import os
import json
import re
import PyPDF2
import google.generativeai as genai
import logging

logger = logging.getLogger(__name__)

def analisar_curriculo_ia(file_stream):
    """
    Recebe um ficheiro PDF, extrai o texto e pede à I.A. para 
    estruturar os dados do candidato (Nome, Email, Telefone, Tags).
    """
    try:
        # 1. Extrair texto do PDF
        reader = PyPDF2.PdfReader(file_stream)
        texto_cv = ""
        # Lê apenas as primeiras 3 páginas para poupar tokens (ninguém tem CV maior que isso)
        for i in range(min(len(reader.pages), 3)):
            texto_cv += reader.pages[i].extract_text() + "\n"
            
        # Reseta o ponteiro do arquivo para que ele possa ser salvo no GCP depois
        file_stream.seek(0)
        
        if not texto_cv.strip():
            return None # PDF vazio ou imagem não pesquisável
            
        # 2. Configurar a I.A. (Google Gemini)
        api_key = os.environ.get("GEMINI_API_KEY")
        if not api_key:
            logger.error("GEMINI_API_KEY não encontrada nas variáveis de ambiente.")
            return None
            
        genai.configure(api_key=api_key)
        # Usamos o modelo Flash por ser super rápido
        model = genai.GenerativeModel('gemini-2.5-flash')
        
        # 3. O Prompt (Instrução para a IA)
        prompt = f"""
        Você é um assistente de Recursos Humanos especialista em ATS.
        Leia o currículo abaixo e extraia as seguintes informações no formato JSON estrito:
        
        {{
            "nome": "Nome completo do candidato",
            "email": "Email do candidato (ou null)",
            "telefone": "Telefone com DDD (ou null)",
            "palavras_chave": "Uma lista com as 5 principais habilidades técnicas ou qualificações do candidato separadas por vírgula (ex: Excel, CNH B, Liderança). Seja muito breve."
        }}
        
        Currículo:
        {texto_cv[:10000]}
        """
        
        # 4. Processar a resposta
        response = model.generate_content(prompt)
        resposta_texto = response.text
        
        # Limpar o texto para garantir que pegamos apenas o JSON (remove ```json ... ```)
        json_match = re.search(r'\{.*\}', resposta_texto, re.DOTALL)
        if json_match:
            dados_extraidos = json.loads(json_match.group(0))
            return dados_extraidos
            
        return None

    except Exception as e:
        logger.error(f"Erro ao analisar CV com I.A.: {e}")
        file_stream.seek(0) # Garante que o ficheiro não fica bloqueado
        return None

