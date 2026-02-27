import face_recognition
import numpy as np
import io

class FaceService:
    def _load_image_from_bytes(self, image_bytes):
        """Lê os bytes brutos do ficheiro nativo e converte para o formato da IA na RAM."""
        image_stream = io.BytesIO(image_bytes)
        # Como o NumPy agora estará na versão 1.26.4, a IA vai conseguir ler isto perfeitamente
        image_array = face_recognition.load_image_file(image_stream)
        return image_array

    def cadastrar_face(self, image_bytes):
        try:
            image_array = self._load_image_from_bytes(image_bytes)
            face_locations = face_recognition.face_locations(image_array)
            
            if len(face_locations) == 0:
                return False, "Nenhum rosto detetado. Fique num local bem iluminado."
            
            if len(face_locations) > 1:
                return False, "Mais de um rosto detetado. Tire a foto sozinho(a)."
                
            face_encodings = face_recognition.face_encodings(image_array, face_locations)
            
            if not face_encodings:
                return False, "Não foi possível mapear o rosto com clareza. Remova os óculos ou chapéu."
                
            encoding_list = face_encodings[0].tolist()
            
            return True, {
                "encoding": encoding_list,
                "image_bytes": image_bytes
            }
            
        except Exception as e:
            print(f"Erro no FaceService (Cadastro): {e}")
            return False, "Erro ao processar a imagem. Tente novamente."

    def reconhecer_face(self, image_bytes, usuarios_empresa):
        try:
            image_array = self._load_image_from_bytes(image_bytes)
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
                
            face_distances = face_recognition.face_distance(known_encodings, unknown_encoding)
            best_match_index = np.argmin(face_distances)
            
            # Tolerância otimizada para portarias (0.60)
            if face_distances[best_match_index] < 0.60:
                return known_user_ids[best_match_index]
                
            return None 
            
        except Exception as e:
            print(f"Erro no FaceService (Reconhecimento): {e}")
            return None

