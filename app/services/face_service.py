import face_recognition
import numpy as np
import io
from PIL import Image
import traceback

class FaceService:
    def _limpar_e_converter_imagem(self, image_bytes):
        """
        LAVAGEM SUPREMA: Cria uma nova matriz limpa do zero e cola a foto do usuário por cima.
        Isso destrói metadados corrompidos, fundos transparentes e erros de strides (fragmentação na RAM).
        Adicionado um log extremo para debug.
        """
        print(f"[DEBUG I.A.] Iniciando processamento da imagem.")
        print(f"[DEBUG I.A.] Tamanho recebido na rede: {len(image_bytes)} bytes.")
        
        try:
            # 1. Abre os bytes com o Pillow apenas para extrair a foto
            img_stream = io.BytesIO(image_bytes)
            imagem_original = Image.open(img_stream)
            print(f"[DEBUG I.A.] Imagem original aberta com sucesso. Formato inicial: {imagem_original.format}, Modo de Cor: {imagem_original.mode}, Resolução: {imagem_original.size}")

            # 2. Força a remoção de canais Alpha (Transparência) se existirem
            if imagem_original.mode in ('RGBA', 'LA') or (imagem_original.mode == 'P' and 'transparency' in imagem_original.info):
                print("[DEBUG I.A.] Imagem possui canal Alpha/Transparência. Removendo...")
                fundo_branco = Image.new('RGB', imagem_original.size, (255, 255, 255))
                fundo_branco.paste(imagem_original, mask=imagem_original.split()[3]) # Cola usando a máscara alpha
                imagem_limpa = fundo_branco
            else:
                # Mesmo que já pareça RGB, força a conversão para garantir
                imagem_limpa = imagem_original.convert('RGB')
                
            print(f"[DEBUG I.A.] Imagem padronizada para modo de cor: {imagem_limpa.mode}")

            # 3. Converte para Matriz NumPY com tipo de dado exato de 8-bits
            matriz_suja = np.array(imagem_limpa, dtype=np.uint8)
            print(f"[DEBUG I.A.] Matriz NumPy criada. Formato dos bits: {matriz_suja.dtype}. Dimensões do array: {matriz_suja.shape}")

            # 4. A BALA DE PRATA: Força a realocação da memória para ser contígua.
            matriz_perfeita = np.ascontiguousarray(matriz_suja)
            
            # Validação do log
            print(f"[DEBUG I.A.] A matriz é contígua na memória RAM? {'Sim (Perfeita)' if matriz_perfeita.flags['C_CONTIGUOUS'] else 'Não (Perigo)'}")
            print(f"[DEBUG I.A.] Fim do pré-processamento. Entregando matriz ao dlib (C++).")

            return matriz_perfeita
            
        except Exception as e:
            print(f"[ERRO CRÍTICO I.A.] Falha durante a limpeza da imagem: {e}")
            traceback.print_exc()
            raise ValueError("Ocorreu um erro ao reconstruir os pixels da imagem.")

    def cadastrar_face(self, image_bytes):
        """
        Lê a foto de cadastro em formato binário nativo, valida as regras e extrai o mapa do rosto.
        Retorna: (sucesso, dados/mensagem)
        """
        try:
            # Substituímos a leitura crua pela nossa nova função de "Lavagem Suprema"
            image_array = self._limpar_e_converter_imagem(image_bytes)
            
            # Encontra todos os rostos na imagem
            face_locations = face_recognition.face_locations(image_array)
            print(f"[DEBUG I.A.] Dlib conseguiu ler a matriz e encontrou {len(face_locations)} rostos.")
            
            # Regras de Negócio e Anti-Fraude
            if len(face_locations) == 0:
                return False, "Nenhum rosto detetado. Fique num local bem iluminado."
            
            if len(face_locations) > 1:
                return False, "Mais de um rosto detetado. Tire a foto sozinho(a)."
                
            # Extrai o "Face Encoding" (o vetor matemático de 128 dimensões único da pessoa)
            face_encodings = face_recognition.face_encodings(image_array, face_locations)
            
            if not face_encodings:
                return False, "Não foi possível mapear o rosto com clareza. Remova os óculos ou chapéu."
                
            # O .tolist() é necessário para conseguirmos salvar o array no banco de dados como JSON
            encoding_list = face_encodings[0].tolist()
            print("[DEBUG I.A.] Extração do vetor de 128 pontos concluída com sucesso.")
            
            return True, {
                "encoding": encoding_list,
                "image_bytes": image_bytes
            }
            
        except Exception as e:
            print(f"Erro no FaceService (Cadastro): {e}")
            return False, "Erro ao processar a imagem. Tente novamente."

    def reconhecer_face(self, image_bytes, usuarios_empresa):
        """
        Compara a foto nativa tirada no Terminal com os mapas salvos no banco de dados.
        Retorna: (user_id do funcionário reconhecido ou None)
        """
        try:
            # Também aplicamos a "Lavagem Suprema" no terminal para garantir
            image_array = self._limpar_e_converter_imagem(image_bytes)
            
            # Acha o rosto na foto do terminal
            face_locations = face_recognition.face_locations(image_array)
            
            if len(face_locations) != 1:
                return None # Ignora se não houver exatamente uma pessoa na frente do tablet
                
            unknown_encoding = face_recognition.face_encodings(image_array, face_locations)[0]
            
            # Prepara a lista de comparação apenas com funcionários desta empresa que já têm biometria
            known_encodings = []
            known_user_ids = []
            
            for user in usuarios_empresa:
                if user.face_encoding:
                    known_encodings.append(np.array(user.face_encoding))
                    known_user_ids.append(user.id)
                    
            if not known_encodings:
                return None # Ninguém na empresa tem biometria cadastrada
                
            # --- OTIMIZAÇÃO VETORIAL ---
            face_distances = face_recognition.face_distance(known_encodings, unknown_encoding)
            
            # Encontra o índice matemático com a menor distância (o rosto mais parecido)
            best_match_index = np.argmin(face_distances)
            
            # Tolerância otimizada para portarias (0.60)
            if face_distances[best_match_index] < 0.60:
                return known_user_ids[best_match_index]
                
            return None # Rosto não reconhecido com a precisão exigida
            
        except Exception as e:
            print(f"Erro no FaceService (Reconhecimento): {e}")
            return None

