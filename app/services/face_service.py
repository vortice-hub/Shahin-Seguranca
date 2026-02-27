import face_recognition
import numpy as np
import io

class FaceService:
    def _load_image_from_bytes(self, image_bytes):
        """Lê os bytes brutos do ficheiro nativo e converte para o formato da IA."""
        # Envolvemos os bytes num ficheiro em memória. 
        # O dlib/face_recognition lida perfeitamente com isto porque é um ficheiro real (sem Base64 corrompido)
        image_stream = io.BytesIO(image_bytes)
        image_array = face_recognition.load_image_file(image_stream)
        return image_array

    def cadastrar_face(self, image_bytes):
        """
        Lê a foto de cadastro em formato binário nativo, valida as regras e extrai o mapa do rosto.
        Retorna: (sucesso, dados/mensagem)
        """
        try:
            image_array = self._load_image_from_bytes(image_bytes)
            
            # Encontra todos os rostos na imagem
            face_locations = face_recognition.face_locations(image_array)
            
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
            image_array = self._load_image_from_bytes(image_bytes)
            
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

