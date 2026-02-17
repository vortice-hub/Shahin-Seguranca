from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

def get_brasil_time():
    """Retorna o horário atual no fuso de Brasília."""
    [span_4](start_span)return datetime.now(pytz.timezone('America/Sao_Paulo'))[span_4](end_span)

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    [span_5](start_span)id = db.Column(db.Integer, primary_key=True)[span_5](end_span)
    [span_6](start_span)username = db.Column(db.String(80), unique=True, nullable=False)[span_6](end_span)
    [span_7](start_span)password_hash = db.Column(db.String(200), nullable=False)[span_7](end_span)
    [span_8](start_span)real_name = db.Column(db.String(120), nullable=False)[span_8](end_span)
    [span_9](start_span)cpf = db.Column(db.String(14), unique=True, nullable=True)[span_9](end_span)
    [span_10](start_span)role = db.Column(db.String(20), default='Funcionario') # Master, Admin, Funcionario, Terminal[span_10](end_span)
    [span_11](start_span)permissions = db.Column(db.String(500), nullable=True) # Ex: "DOCUMENTOS,PONTO,ESTOQUE"[span_11](end_span)
    [span_12](start_span)is_first_access = db.Column(db.Boolean, default=True)[span_12](end_span)
    
    # Dados de Ponto
    [span_13](start_span)carga_horaria = db.Column(db.Integer, default=528)[span_13](end_span)
    [span_14](start_span)tempo_intervalo = db.Column(db.Integer, default=60)[span_14](end_span)
    [span_15](start_span)inicio_jornada_ideal = db.Column(db.String(5), default="08:00")[span_15](end_span)
    [span_16](start_span)escala = db.Column(db.String(20), default="Livre")[span_16](end_span)
    [span_17](start_span)data_inicio_escala = db.Column(db.Date, nullable=True)[span_17](end_span)
    
    # Dados Financeiros
    [span_18](start_span)salario = db.Column(db.Float, default=0.0)[span_18](end_span)
    [span_19](start_span)razao_social_empregadora = db.Column(db.String(200))[span_19](end_span)
    [span_20](start_span)cnpj_empregador = db.Column(db.String(20))[span_20](end_span)

    def set_password(self, password):
        [span_21](start_span)self.password_hash = generate_password_hash(password)[span_21](end_span)

    def check_password(self, password):
        [span_22](start_span)return check_password_hash(self.password_hash, password)[span_22](end_span)

class PreCadastro(db.Model):
    """Modelo para armazenar CPFs liberados para cadastro inicial."""
    __tablename__ = 'pre_cadastros'
    id = db.Column(db.Integer, primary_key=True)
    [span_23](start_span)[span_24](start_span)cpf = db.Column(db.String(14), unique=True, nullable=False)[span_23](end_span)[span_24](end_span)
    [span_25](start_span)[span_26](start_span)nome_previsto = db.Column(db.String(120), nullable=False)[span_25](end_span)[span_26](end_span)
    [span_27](start_span)[span_28](start_span)cargo = db.Column(db.String(80))[span_27](end_span)[span_28](end_span)
    [span_29](start_span)[span_30](start_span)salario = db.Column(db.Float, default=0.0)[span_29](end_span)[span_30](end_span)
    [span_31](start_span)[span_32](start_span)razao_social = db.Column(db.String(200))[span_31](end_span)[span_32](end_span)
    [span_33](start_span)[span_34](start_span)cnpj = db.Column(db.String(20))[span_33](end_span)[span_34](end_span)
    [span_35](start_span)[span_36](start_span)carga_horaria = db.Column(db.Integer, default=528)[span_35](end_span)[span_36](end_span)
    [span_37](start_span)[span_38](start_span)tempo_intervalo = db.Column(db.Integer, default=60)[span_37](end_span)[span_38](end_span)
    [span_39](start_span)[span_40](start_span)inicio_jornada_ideal = db.Column(db.String(5), default="08:00")[span_39](end_span)[span_40](end_span)
    [span_41](start_span)[span_42](start_span)escala = db.Column(db.String(20), default="Livre")[span_41](end_span)[span_42](end_span)
    [span_43](start_span)[span_44](start_span)data_inicio_escala = db.Column(db.Date, nullable=True)[span_43](end_span)[span_44](end_span)
    created_at = db.Column(db.DateTime, default=get_brasil_time)

class Holerite(db.Model):
    __tablename__ = 'holerites'
    [span_45](start_span)id = db.Column(db.Integer, primary_key=True)[span_45](end_span)
    [span_46](start_span)user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)[span_46](end_span)
    [span_47](start_span)mes_referencia = db.Column(db.String(7), nullable=False)[span_47](end_span)
    [span_48](start_span)status = db.Column(db.String(20), default='Enviado') # 'Enviado' ou 'Revisao'[span_48](end_span)
    [span_49](start_span)url_arquivo = db.Column(db.String(500), nullable=True)[span_49](end_span)
    [span_50](start_span)conteudo_pdf = db.Column(db.LargeBinary, nullable=True)[span_50](end_span)
    [span_51](start_span)visualizado = db.Column(db.Boolean, default=False)[span_51](end_span)
    [span_52](start_span)visualizado_em = db.Column(db.DateTime, nullable=True)[span_52](end_span)
    [span_53](start_span)enviado_em = db.Column(db.DateTime, default=get_brasil_time)[span_53](end_span)

    [span_54](start_span)user = db.relationship('User', backref=db.backref('holerites', lazy=True))[span_54](end_span)

class Recibo(db.Model):
    __tablename__ = 'recibos'
    [span_55](start_span)id = db.Column(db.Integer, primary_key=True)[span_55](end_span)
    [span_56](start_span)user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)[span_56](end_span)
    [span_57](start_span)valor = db.Column(db.Float, nullable=False)[span_57](end_span)
    [span_58](start_span)data_pagamento = db.Column(db.Date, nullable=False)[span_58](end_span)
    [span_59](start_span)tipo_vale_alimentacao = db.Column(db.Boolean, default=False)[span_59](end_span)
    [span_60](start_span)tipo_vale_transporte = db.Column(db.Boolean, default=False)[span_60](end_span)
    [span_61](start_span)tipo_assiduidade = db.Column(db.Boolean, default=False)[span_61](end_span)
    [span_62](start_span)tipo_cesta_basica = db.Column(db.Boolean, default=False)[span_62](end_span)
    [span_63](start_span)forma_pagamento = db.Column(db.String(50), default="Transferência")[span_63](end_span)
    [span_64](start_span)conteudo_pdf = db.Column(db.LargeBinary, nullable=True)[span_64](end_span)
    [span_65](start_span)visualizado = db.Column(db.Boolean, default=False)[span_65](end_span)
    [span_66](start_span)created_at = db.Column(db.DateTime, default=get_brasil_time)[span_66](end_span)

    [span_67](start_span)user = db.relationship('User', backref=db.backref('recibos', lazy=True))[span_67](end_span)

class AssinaturaDigital(db.Model):
    __tablename__ = 'assinaturas_digitais'
    [span_68](start_span)id = db.Column(db.Integer, primary_key=True)[span_68](end_span)
    [span_69](start_span)user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)[span_69](end_span)
    [span_70](start_span)tipo_documento = db.Column(db.String(50), nullable=False)[span_70](end_span)
    [span_71](start_span)documento_id = db.Column(db.Integer, nullable=False)[span_71](end_span)
    [span_72](start_span)hash_arquivo = db.Column(db.String(128), nullable=False)[span_72](end_span)
    [span_73](start_span)ip_address = db.Column(db.String(45))[span_73](end_span)
    [span_74](start_span)user_agent = db.Column(db.String(255))[span_74](end_span)
    [span_75](start_span)data_assinatura = db.Column(db.DateTime, default=get_brasil_time)[span_75](end_span)

    [span_76](start_span)user = db.relationship('User', backref=db.backref('assinaturas', lazy=True))[span_76](end_span)

class PontoRegistro(db.Model):
    __tablename__ = 'ponto_registros'
    [span_77](start_span)id = db.Column(db.Integer, primary_key=True)[span_77](end_span)
    [span_78](start_span)user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)[span_78](end_span)
    [span_79](start_span)data_registro = db.Column(db.Date, nullable=False)[span_79](end_span)
    [span_80](start_span)hora_registro = db.Column(db.Time, nullable=False)[span_80](end_span)
    [span_81](start_span)tipo = db.Column(db.String(20)) # Entrada, Saída, etc[span_81](end_span)
    [span_82](start_span)latitude = db.Column(db.String(50))[span_82](end_span)
    [span_83](start_span)longitude = db.Column(db.String(50))[span_83](end_span)

class PontoResumo(db.Model):
    __tablename__ = 'ponto_resumos'
    [span_84](start_span)id = db.Column(db.Integer, primary_key=True)[span_84](end_span)
    [span_85](start_span)user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)[span_85](end_span)
    [span_86](start_span)data_referencia = db.Column(db.Date, nullable=False)[span_86](end_span)
    [span_87](start_span)minutos_trabalhados = db.Column(db.Integer, default=0)[span_87](end_span)
    [span_88](start_span)minutos_extras = db.Column(db.Integer, default=0)[span_88](end_span)
    [span_89](start_span)minutos_falta = db.Column(db.Integer, default=0)[span_89](end_span)
    [span_90](start_span)saldo_dia = db.Column(db.Integer, default=0)[span_90](end_span)
    [span_91](start_span)status_dia = db.Column(db.String(20), default='OK') # OK, Falta, Incompleto, etc[span_91](end_span)

class PontoAjuste(db.Model):
    __tablename__ = 'ponto_ajustes'
    [span_92](start_span)id = db.Column(db.Integer, primary_key=True)[span_92](end_span)
    [span_93](start_span)user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)[span_93](end_span)
    [span_94](start_span)data_referencia = db.Column(db.Date, nullable=False)[span_94](end_span)
    [span_95](start_span)ponto_original_id = db.Column(db.Integer, nullable=True)[span_95](end_span)
    [span_96](start_span)novo_horario = db.Column(db.String(5))[span_96](end_span)
    [span_97](start_span)tipo_batida = db.Column(db.String(20))[span_97](end_span)
    [span_98](start_span)tipo_solicitacao = db.Column(db.String(20)) # Inclusao, Edicao, Exclusao[span_98](end_span)
    [span_99](start_span)justificativa = db.Column(db.Text)[span_99](end_span)
    [span_100](start_span)status = db.Column(db.String(20), default='Pendente')[span_100](end_span)
    [span_101](start_span)motivo_reprovacao = db.Column(db.Text)[span_101](end_span)
    [span_102](start_span)created_at = db.Column(db.DateTime, default=get_brasil_time)[span_102](end_span)
    
    user = db.relationship('User', backref=db.backref('ajustes', lazy=True))

