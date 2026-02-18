from google.cloud import vision
import re
import unicodedata

def limpar_texto(texto):
    """Remove acentos e padroniza o texto para facilitar a busca do nome."""
    if not texto: return ""
    texto = "".join(c for c in unicodedata.normalize('NFD', texto) if unicodedata.category(c) != 'Mn')
    return texto.upper().replace('\n', ' ').strip()

def analisar_atestado_vision(imagem_bytes, nome_funcionario):
    """Usa o Google Cloud Vision para ler o atestado e extrair os dados."""
    dados = {
        "nome_encontrado": False,
        "data_inicio": None,
        "dias_afastamento": None,
        "texto_bruto": ""
    }
    
    try:
        # Chama a API do Google Vision
        client = vision.ImageAnnotatorClient()
        image = vision.Image(content=imagem_bytes)
        response = client.text_detection(image=image)
        
        if response.error.message:
            print(f"Erro na API Vision: {response.error.message}")
            return dados

        textos = response.text_annotations
        if not textos:
            return dados
        
        # O primeiro item contém todo o texto detectado na imagem
        texto_completo = textos[0].description
        dados["texto_bruto"] = texto_completo
        
        texto_limpo = limpar_texto(texto_completo)
        nome_limpo = limpar_texto(nome_funcionario)

        # 1. Verifica se o nome do funcionário está no atestado
        # Divide o nome e verifica se pelo menos o Primeiro e Último nome aparecem
        partes_nome = nome_limpo.split()
        if len(partes_nome) >= 2:
            if partes_nome[0] in texto_limpo and partes_nome[-1] in texto_limpo:
                dados["nome_encontrado"] = True
        elif nome_limpo in texto_limpo:
             dados["nome_encontrado"] = True

        # 2. Busca a quantidade de dias (Ex: "03 dias", "repouso de 2 dias")
        match_dias = re.search(r'(\d+)\s*(DIAS|DIA)', texto_limpo)
        if match_dias:
            dados["dias_afastamento"] = int(match_dias.group(1))

        # 3. Busca a data de emissão (assumindo como data de início)
        match_data = re.search(r'(\d{2})[/\-](\d{2})[/\-](\d{4})', texto_limpo)
        if match_data:
            dia, mes, ano = match_data.group(1), match_data.group(2), match_data.group(3)
            dados["data_inicio"] = f"{ano}-{mes}-{dia}"

        return dados

    except Exception as e:
        print(f"Falha ao processar OCR do atestado: {e}")
        return dados

