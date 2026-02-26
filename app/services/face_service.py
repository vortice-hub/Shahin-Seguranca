import face_recognition
import numpy as np
import base64
import io
from PIL import Image

class FaceService:
    def _decode_base64_image(self, base64_str):
        """Converte a string base64 do frontend num formato que a IA consiga ler."""
        # Remove o cabeçalho 'data:image/jpeg;base64,' se existir
        if ',' in base64_str:
            base64_str = base64_str.split(',')[1]
            
        img_data = base64.b64decode(base64_str)
        image = Image.open(io.BytesIO(img_data))
        
        # O face_recognition exige imagens no formato RGB
        if image.mode != "RGB":
            image = image.convert("RGB")
            
        return np.array(image), img_data

    def cadastrar_face(self, base64_image):
        """
        Lê a foto de cadastro, valida as regras e extrai o mapa do rosto.
        Retorna: (sucesso, dados/mensagem)
        """
        try:
            image_array, raw_bytes = self._decode_base64_image(base64_image)
            
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
                "image_bytes": raw_bytes
            }
            
        except Exception as e:
            print(f"Erro no FaceService (Cadastro): {e}")
            return False, "Erro ao processar a imagem. Tente novamente."

    def reconhecer_face(self, base64_image, usuarios_empresa):
        """
        Compara a foto tirada no Terminal com os mapas salvos no banco de dados usando busca vetorizada otimizada.
        Retorna: (user_id do funcionário reconhecido ou None)
        """
        try:
            image_array, _ = self._decode_base64_image(base64_image)
            
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
            # A função face_distance do NumPy compara 'unknown_encoding' contra TODOS os 'known_encodings' simultaneamente.
            face_distances = face_recognition.face_distance(known_encodings, unknown_encoding)
            
            # Encontra o índice matemático com a menor distância (o rosto mais parecido)
            best_match_index = np.argmin(face_distances)
            
            # --- A MÁGICA ACONTECE AQUI ---
            # Alterado de 0.50 para 0.60. Agora o sistema é mais tolerante com iluminação e ângulos,
            # tornando o uso diário muito mais fácil e fluido para os funcionários.
            if face_distances[best_match_index] < 0.60:
                return known_user_ids[best_match_index]
                
            return None # Rosto não reconhecido com a precisão exigida
            
        except Exception as e:
            print(f"Erro no FaceService (Reconhecimento): {e}")
            return None

