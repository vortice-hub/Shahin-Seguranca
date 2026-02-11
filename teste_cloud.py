import cloudinary
import cloudinary.uploader

# Suas credenciais (Peguei da URL que você mandou antes)
cloudinary.config(
  cloud_name = "dxb4fbdjy",
  api_key = "537342766187832",
  api_secret = "cbINpCjQtRh7oKp-uVX2YPdOKaI"
)

print("--- INICIANDO TESTE DE DIAGNOSTICO ---")

try:
    # Cria um arquivo dummy
    with open("teste.txt", "w") as f:
        f.write("Teste de conexao TdS")

    print("1. Tentando upload como RAW (Arquivo Bruto)...")
    resp = cloudinary.uploader.upload("teste.txt", resource_type="raw", public_id="teste_diagnostico.txt")
    
    print("\n>>> RESPOSTA DO CLOUDINARY:")
    print(resp)
    print("\n>>> URL GERADA:")
    print(resp.get('secure_url'))
    print("\n------------------------------------------------")
    print("SE VOCE VER A URL ACIMA, A CONEXAO ESTA OK.")
    print("Tente clicar no link gerado. Se baixar, o problema era o codigo, nao a conta.")
    
except Exception as e:
    print(f"\nERRO FATAL: {e}")


