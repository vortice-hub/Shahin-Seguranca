import random
import string
from datetime import datetime
from app.models import (AssinaturaDigital, Atestado, Notificacao, PushSubscription, 
                        PontoAjuste, PeriodoAquisitivo, SolicitacaoAusencia, 
                        SolicitacaoUniforme, PontoRegistro, PontoResumo, Holerite, Recibo, PreCadastro)
from app.repositories.user_repository import UserRepository, PreCadastroRepository
from app.utils import time_to_minutes

class UserService:
    def __init__(self):
        self.user_repo = UserRepository()
        self.pre_repo = PreCadastroRepository()

    def criar_pre_cadastro(self, form_data):
        cpf = form_data.get('cpf', '').replace('.', '').replace('-', '').strip()
        real_name = form_data.get('real_name')
        
        if not real_name or not cpf:
            raise ValueError("Nome e CPF são obrigatórios.")
            
        if self.user_repo.get_by_cpf(cpf) or self.pre_repo.get_by_cpf(cpf):
            raise ValueError("CPF já cadastrado!")

        dt_adm_str = form_data.get('data_admissao')
        dt_admissao = datetime.strptime(dt_adm_str, '%Y-%m-%d').date() if dt_adm_str else None

        carga_hm = form_data.get('carga_horaria') or '08:48'
        carga_minutos = time_to_minutes(carga_hm)
        intervalo_min = int(form_data.get('tempo_intervalo') or 60)
        cpf_gestor = form_data.get('cpf_gestor', '').replace('.', '').replace('-', '').strip()

        novo_pre = PreCadastro(
            cpf=cpf, nome_previsto=real_name, cargo=form_data.get('role'),
            departamento=form_data.get('departamento'), cpf_gestor=cpf_gestor if cpf_gestor else None,
            salario=float(form_data.get('salario') or 0), razao_social=form_data.get('razao_social'),
            cnpj=form_data.get('cnpj'), data_admissao=dt_admissao, carga_horaria=carga_minutos,
            tempo_intervalo=intervalo_min, inicio_jornada_ideal=form_data.get('h_ent') or '08:00',
            escala=form_data.get('escala'), data_inicio_escala=form_data.get('dt_escala') if form_data.get('dt_escala') else None
        )
        self.pre_repo.add(novo_pre)
        self.pre_repo.commit()
        return real_name, cpf

    def excluir_usuario(self, user):
        if user.username == '50097952800' or user.username == 'Thaynara':
            raise ValueError('Impossível excluir Master da empresa.')
            
        try:
            # 1. Liberta subordinados
            subordinados = self.user_repo.get_subordinados(user.id)
            for sub in subordinados:
                sub.gestor_id = None
                
            # 2. Limpeza Profunda (Garantindo que apagamos tudo relacionado a ele)
            AssinaturaDigital.query.filter_by(user_id=user.id).delete()
            Atestado.query.filter_by(user_id=user.id).delete()
            Notificacao.query.filter_by(user_id=user.id).delete()
            PushSubscription.query.filter_by(user_id=user.id).delete()
            PontoAjuste.query.filter_by(user_id=user.id).delete()
            PeriodoAquisitivo.query.filter_by(user_id=user.id).delete()
            SolicitacaoAusencia.query.filter_by(user_id=user.id).delete()
            SolicitacaoUniforme.query.filter_by(user_id=user.id).delete()
            PontoRegistro.query.filter_by(user_id=user.id).delete()
            PontoResumo.query.filter_by(user_id=user.id).delete()
            Holerite.query.filter_by(user_id=user.id).delete()
            Recibo.query.filter_by(user_id=user.id).delete()
            
            # 3. Exclui o utilizador e faz o commit
            self.user_repo.delete(user)
            self.user_repo.commit()
        except Exception as e:
            self.user_repo.rollback()
            raise e

    def atualizar_usuario(self, user, form_data):
        user.real_name = form_data.get('real_name')
        user.role = form_data.get('role')
        user.departamento = form_data.get('departamento')
        
        gestor_req = form_data.get('gestor_id')
        user.gestor_id = int(gestor_req) if gestor_req else None
        
        user.salario = float(form_data.get('salario') or 0)
        user.razao_social_empregadora = form_data.get('razao_social')
        user.cnpj_empregador = form_data.get('cnpj')
        
        dt_adm_str = form_data.get('data_admissao')
        if dt_adm_str: 
            user.data_admissao = datetime.strptime(dt_adm_str, '%Y-%m-%d').date()
        
        user.carga_horaria = time_to_minutes(form_data.get('carga_horaria'))
        user.tempo_intervalo = int(form_data.get('tempo_intervalo') or 60)
        user.inicio_jornada_ideal = form_data.get('h_ent')
        user.escala = form_data.get('escala')
        if form_data.get('dt_escala'): 
            user.data_inicio_escala = form_data.get('dt_escala')

        if user.username != '50097952800' and user.username != 'Thaynara':
            lista_perms = form_data.getlist('perm_keys')
            user.permissions = ",".join(lista_perms)
        
        self.user_repo.commit()

    def resetar_senha(self, user):
        senha_temporaria = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        user.set_password(senha_temporaria)
        user.is_first_access = True
        self.user_repo.commit()
        return senha_temporaria

