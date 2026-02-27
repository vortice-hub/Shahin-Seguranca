import face_recognition
import io
import os
import uuid
from PIL import Image
import traceback

class FaceService:
    def _salvar_e_carregar_imagem(self, image_bytes):
        """
        BYPASS SUPREMO: Como a instalação do dlib no servidor recusa matrizes perfeitas da RAM,
        nós usamos o Pillow para garantir que a imagem não tem canal Alpha,
        salvamos a imagem LIMPA fisicamente no disco e obrigamos a IA a lê-la do disco.
        """
        print(f"[DEBUG I.A.] Iniciando processamento da imagem (Bypass de Disco).")
        print(f"[DEBUG I.A.] Tamanho recebido: {len(image_bytes)} bytes.")
        
        temp_filename = f"/tmp/biometria_{uuid.uuid4().hex}.jpg"
        
        try:
            # 1. Abre a imagem original
            img_stream = io.BytesIO(image_bytes)
            imagem_original = Image.open(img_stream)
            
            # 2. Força a conversão para RGB puro (mata transparências e metadados lixo)
            if imagem_original.mode != 'RGB':
                print(f"[DEBUG I.A.] Convertendo imagem de {imagem_original.mode} para RGB.")
                if imagem_original.mode in ('RGBA', 'LA') or (imagem_original.mode == 'P' and 'transparency' in imagem_original.info):
                    fundo_branco = Image.new('RGB', imagem_original.size, (255, 255, 255))
                    fundo_branco.paste(imagem_original, mask=imagem_original.split()[-1])
                    imagem_limpa = fundo_branco
                else:
                    imagem_limpa = imagem_original.convert('RGB')
            else:
                imagem_limpa = imagem_original

            # 3. Salva a imagem limpa e perfeita no disco físico do servidor
            imagem_limpa.save(temp_filename, format="JPEG", quality=100)
            print(f"[DEBUG I.A.] Imagem limpa salva fisicamente em: {temp_filename}")
            
            # 4. A BALA DE PRATA: O motor C++ é forçado a ler do disco, evitando os bugs de RAM
            print("[DEBUG I.A.] Solicitando leitura pelo motor C++ (face_recognition.load_image_file)")
            image_array = face_recognition.load_image_file(temp_filename)
            
            print("[DEBUG I.A.] Motor C++ engoliu a imagem com sucesso.")
            return image_array

        except Exception as e:
            print(f"[ERRO CRÍTICO I.A.] Falha durante o processamento de disco: {e}")
            traceback.print_exc()
            raise ValueError("Ocorreu um erro ao preparar a imagem para a Inteligência Artificial.")
            
        finally:
            # 5. Destrói o arquivo físico para não lotar o servidor, independentemente de dar erro ou não
            if os.path.exists(temp_filename):
                os.remove(temp_filename)
                print(f"[DEBUG I.A.] Ficheiro temporário {temp_filename} apagado da raiz.")

    def cadastrar_face(self, image_bytes):
        """
        Lê a foto de cadastro, valida as regras e extrai o mapa do rosto.
        Retorna: (sucesso, dados/mensagem)
        """
        try:
            image_array = self._salvar_e_carregar_imagem(image_bytes)
            
            # Encontra todos os rostos na imagem
            face_locations = face_recognition.face_locations(image_array)
            print(f"[DEBUG I.A.] Dlib encontrou {len(face_locations)} rosto(s) na imagem.")
            
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
            print("[DEBUG I.A.] Extração matemática dos 128 pontos concluída com sucesso.")
            
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
            image_array = self._salvar_e_carregar_imagem(image_bytes)
            
            # Acha o rosto na foto do terminal
            face_locations = face_recognition.face_locations(image_array)
            
            if len(face_locations) != 1:
                return None 
                
            unknown_encoding = face_recognition.face_encodings(image_array, face_locations)[0]
            
            known_encodings = []
            known_user_ids = []
            
            for user in usuarios_empresa:
                if user.face_encoding:
                    known_encodings.append(np.array(user.face_encoding))
                    known_user_ids.append(user.id)
                    
            if not known_encodings:
                return None 
                
            # --- OTIMIZAÇÃO VETORIAL ---
            face_distances = face_recognition.face_distance(known_encodings, unknown_encoding)
            
            best_match_index = np.argmin(face_distances)
            
            # Tolerância otimizada para portarias (0.60)
            if face_distances[best_match_index] < 0.60:
                return known_user_ids[best_match_index]
                
            return None
            
        except Exception as e:
            print(f"Erro no FaceService (Reconhecimento): {e}")
            return None

