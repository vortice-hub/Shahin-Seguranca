import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from sqlalchemy import text

app = Flask(__name__)
app.secret_key = 'chave_secreta_thay_rh'

# Configuração DB
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELOS ---
class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    genero = db.Column(db.String(20)) # Novo campo
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

class HistoricoEntrada(db.Model):
    __tablename__ = 'historico_entrada'
    id = db.Column(db.Integer, primary_key=True)
    item_nome = db.Column(db.String(150)) # Guardamos o nome caso o item seja deletado
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

# --- MIGRACAO AUTOMATICA SIMPLES ---
def update_db_schema():
    with app.app_context():
        # Tenta criar tabelas que nao existem
        db.create_all()
        
        # Tenta adicionar coluna genero se nao existir (Migracao Manual)
        try:
            with db.engine.connect() as conn:
                conn.execute(text("ALTER TABLE itens_estoque ADD COLUMN IF NOT EXISTS genero VARCHAR(20)"))
                conn.commit()
        except Exception as e:
            print(f"Aviso DB: {e}")

update_db_schema()

# --- ROTAS ---

@app.route('/')
def dashboard():
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('dashboard.html', itens=itens)

# --- FLUXO DE ENTRADA ---
@app.route('/entrada', methods=['GET', 'POST'])
def entrada():
    if request.method == 'POST':
        nome = request.form.get('nome')
        categoria = request.form.get('categoria')
        tamanho = request.form.get('tamanho')
        genero = request.form.get('genero')
        quantidade = int(request.form.get('quantidade'))
        
        # Verifica se item ja existe (mesmo nome, tamanho e genero)
        item = ItemEstoque.query.filter_by(nome=nome, tamanho=tamanho, genero=genero).first()
        
        if item:
            item.quantidade += quantidade
            item.data_atualizacao = datetime.utcnow()
            flash(f'Adicionado +{quantidade} ao estoque de {nome}.')
        else:
            novo_item = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, genero=genero, quantidade=quantidade)
            db.session.add(novo_item)
            flash(f'Novo item {nome} criado com sucesso.')
            
        # Log Historico
        log = HistoricoEntrada(item_nome=f"{nome} ({genero} - {tamanho})", quantidade=quantidade)
        db.session.add(log)
        
        db.session.commit()
        return redirect(url_for('entrada'))
        
    # GET: Lista itens existentes para facilitar preenchimento (opcional, ou apenas form limpo)
    return render_template('entrada.html')

@app.route('/historico/entrada')
def view_historico_entrada():
    logs = HistoricoEntrada.query.order_by(HistoricoEntrada.data_hora.desc()).all()
    return render_template('historico_entrada.html', logs=logs)

# --- FLUXO DE SAIDA ---
@app.route('/saida', methods=['GET', 'POST'])
def saida():
    if request.method == 'POST':
        item_id = request.form.get('item_id')
        coordenador = request.form.get('coordenador')
        colaborador = request.form.get('colaborador')
        data_input = request.form.get('data')
        
        item = ItemEstoque.query.get(item_id)
        
        if item and item.quantidade > 0:
            item.quantidade -= 1 # Assume saida unitaria ou adicionar campo qtd
            item.data_atualizacao = datetime.utcnow()
            
            # Log Historico
            # Converte string data input para datetime se necessario, ou usa data atual se vazio
            data_final = datetime.strptime(data_input, '%Y-%m-%d') if data_input else datetime.utcnow()
            
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
            
    itens_disponiveis = ItemEstoque.query.filter(ItemEstoque.quantidade > 0).order_by(ItemEstoque.nome).all()
    return render_template('saida.html', itens=itens_disponiveis)

@app.route('/historico/saida')
def view_historico_saida():
    logs = HistoricoSaida.query.order_by(HistoricoSaida.data_entrega.desc()).all()
    return render_template('historico_saida.html', logs=logs)

if __name__ == '__main__':
    app.run(debug=True)