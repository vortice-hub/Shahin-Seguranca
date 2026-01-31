import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text

app = Flask(__name__)

# --- CONFIGURAÇÃO DE SEGURANÇA E BANCO ---

# 1. Secret Key: Tenta pegar do ambiente, senão usa uma fixa
app.secret_key = os.environ.get('SECRET_KEY', 'thay_rh_dev_key_fallback')

# 2. Banco de Dados Híbrido
# Tenta pegar a variável DATABASE_URL do Render.
# Se não existir (None), usa a string hardcoded como 'Fallback' para o site não cair.
db_url_env = os.environ.get('DATABASE_URL')
db_fallback = 'postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require'

if db_url_env:
    # Correção para URLs postgres antigas que começam com postgres://
    if db_url_env.startswith("postgres://"):
        db_url_env = db_url_env.replace("postgres://", "postgresql://", 1)
    app.config['SQLALCHEMY_DATABASE_URI'] = db_url_env
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = db_fallback

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# 3. Correção de Queda de Conexão (SSL Error)
# 'pool_pre_ping': Testa a conexão antes de usar.
# 'pool_recycle': Recicla conexões a cada 300 segundos (5 min).
db = SQLAlchemy(app, engine_options={
    "pool_pre_ping": True, 
    "pool_recycle": 300
})

# --- MODELOS DO BANCO ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) 
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150))
    quantidade = db.Column(db.Integer)
    data_hora = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoSaida(db.Model):
    __tablename__ = 'historico_saida'
    id = db.Column(db.Integer, primary_key=True)
    coordenador = db.Column(db.String(100))
    colaborador = db.Column(db.String(100))
    item_nome = db.Column(db.String(100))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20))
    quantidade = db.Column(db.Integer)
    data_entrega = db.Column(db.DateTime, default=datetime.utcnow)

# --- FUNÇÃO DE MIGRAÇÃO SEGURA ---
def check_database():
    with app.app_context():
        try:
            db.create_all()
            # Tenta adicionar coluna genero manualmente caso não exista
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.commit()
        except Exception as e:
            # Erros de migração não devem parar o app
            print(f"DB Check Warning: {e}")

# Executa verificação ao iniciar
check_database()

# --- ROTAS ---

@app.route('/')
def dashboard():
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('dashboard.html', itens=itens)

@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        nome = request.form.get('nome')
        categoria = request.form.get('categoria')
        tamanho = request.form.get('tamanho')
        genero = request.form.get('genero')
        try:
            quantidade = int(request.form.get('quantidade'))
        except:
            quantidade = 1
        
        item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
        
        if item:
            item.quantidade += quantidade
            item.data_atualizacao = datetime.utcnow()
            flash(f'Estoque atualizado: {nome} (+{quantidade})')
        else:
            novo_item = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, genero=genero, quantidade=quantidade)
            db.session.add(novo_item)
            flash(f'Novo item cadastrado: {nome}')
            
        log = HistoricoEntrada(item_nome=f"{nome} ({genero} - {tamanho})", quantidade=quantidade)
        db.session.add(log)
        db.session.commit()
        return redirect(url_for('entrada'))
        
    return render_template('entrada.html')

@app.route('/historico/entrada')
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

@app.route('/saida', methods=['GET', 'POST'])
def saida():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        coordenador = request.form.get('coordenador')
        colaborador = request.form.get('colaborador')
        data_input = request.form.get('data')
        
        if not item_id:
            flash("Erro: Selecione um item.")
            return redirect(url_for('saida'))

        item = ItemEstoque.query.get(item_id)
        
        if item and item.quantidade > 0:
            item.quantidade -= 1
            item.data_atualizacao = datetime.utcnow()
            
            try:
                data_final = datetime.strptime(data_input, '%Y-%m-%d')
            except:
                data_final = datetime.utcnow()
            
            log = HistoricoSaida(
                coordenador=coordenador,
                colaborador=colaborador,
                item_nome=item.nome,
                tamanho=item.tamanho,
                genero=item.genero,
                quantidade=1,
                data_entrega=data_final
            )
            db.session.add(log)
            db.session.commit()
            flash('Entrega registrada com sucesso!')
            return redirect(url_for('dashboard'))
        else:
            flash('Erro: Item não encontrado ou estoque zerado.')
            return redirect(url_for('saida'))
            
    itens_disponiveis = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
    return render_template('saida.html', itens=itens_disponiveis)

@app.route('/historico/saida')
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

if __name__ == '__main__':
    app.run(debug=True)