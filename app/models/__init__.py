from app.extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
import pytz

def get_brasil_time():
    return datetime.now(pytz.timezone('America/Sao_Paulo'))

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    real_name = db.Column(db.String(120), nullable=False)
    cpf = db.Column(db.String(14), unique=True, nullable=True)
    role = db.Column(db.String(20), default='Funcionario') # Master, Admin, Funcionario, Terminal
    permissions = db.Column(db.String(500), nullable=True) # Ex: "DOCUMENTOS,PONTO,ESTOQUE"
    is_first_access = db.Column(db.Boolean, default=True)
    
    # Dados de Ponto
    carga_horaria = db.Column(db.Integer, default=528)
    tempo_intervalo = db.Column(db.Integer, default=60)
    inicio_jornada_ideal = db.Column(db.String(5), default="08:00")
    escala = db.Column(db.String(20), default="Livre")
    data_inicio_escala = db.Column(db.Date, nullable=True)
    
    # Dados Financeiros
    salario = db.Column(db.Float, default=0.0)
    razao_social_empregadora = db.Column(db.String(200))
    cnpj_empregador = db.Column(db.String(20))

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Holerite(db.Model):
    __tablename__ = 'holerites'
    id = db.Column(db.Integer, primary_key=True)
    # user_id agora aceita NULL (None) para quando a IA não identifica o nome de primeira
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    mes_referencia = db.Column(db.String(7), nullable=False) 
    
    # Colunas novas para GCS e Revisão
    status = db.Column(db.String(20), default='Enviado') # 'Enviado' ou 'Revisao'
    url_arquivo = db.Column(db.String(500), nullable=True) 
    
    conteudo_pdf = db.Column(db.LargeBinary, nullable=True) 
    visualizado = db.Column(db.Boolean, default=False)
    visualizado_em = db.Column(db.DateTime, nullable=True)
    enviado_em = db.Column(db.DateTime, default=get_brasil_time)

    user = db.relationship('User', backref=db.backref('holerites', lazy=True))

class Recibo(db.Model):
    __tablename__ = 'recibos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    valor = db.Column(db.Float, nullable=False)
    data_pagamento = db.Column(db.Date, nullable=False)
    
    tipo_vale_alimentacao = db.Column(db.Boolean, default=False)
    tipo_vale_transporte = db.Column(db.Boolean, default=False)
    tipo_assiduidade = db.Column(db.Boolean, default=False)
    tipo_cesta_basica = db.Column(db.Boolean, default=False)
    
    forma_pagamento = db.Column(db.String(50), default="Transferência")
    conteudo_pdf = db.Column(db.LargeBinary, nullable=True)
    visualizado = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=get_brasil_time)

    user = db.relationship('User', backref=db.backref('recibos', lazy=True))

class AssinaturaDigital(db.Model):
    __tablename__ = 'assinaturas_digitais'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    tipo_documento = db.Column(db.String(50), nullable=False) 
    documento_id = db.Column(db.Integer, nullable=False)
    hash_arquivo = db.Column(db.String(128), nullable=False)
    ip_address = db.Column(db.String(45))
    user_agent = db.Column(db.String(255))
    data_assinatura = db.Column(db.DateTime, default=get_brasil_time)

    user = db.relationship('User', backref=db.backref('assinaturas', lazy=True))

# Registros de Ponto
class PontoRegistro(db.Model):
    __tablename__ = 'ponto_registros'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_registro = db.Column(db.Date, nullable=False)
    hora_registro = db.Column(db.Time, nullable=False)
    tipo = db.Column(db.String(20)) # Entrada, Saída, etc
    latitude = db.Column(db.String(50))
    longitude = db.Column(db.String(50))

class PontoResumo(db.Model):
    __tablename__ = 'ponto_resumos'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    minutos_trabalhados = db.Column(db.Integer, default=0)
    minutos_extras = db.Column(db.Integer, default=0)
    minutos_falta = db.Column(db.Integer, default=0)
    saldo_dia = db.Column(db.Integer, default=0)

class PontoAjuste(db.Model):
    __tablename__ = 'ponto_ajustes'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    data_referencia = db.Column(db.Date, nullable=False)
    ponto_original_id = db.Column(db.Integer, nullable=True)
    novo_horario = db.Column(db.String(5))
    tipo_batida = db.Column(db.String(20))
    tipo_solicitacao = db.Column(db.String(20)) # Inclusao, Edicao, Exclusao
    justificativa = db.Column(db.Text)
    status = db.Column(db.String(20), default='Pendente')
    motivo_reprovacao = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=get_brasil_time)