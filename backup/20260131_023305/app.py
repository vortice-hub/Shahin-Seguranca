import os
from flask import Flask, render_template, request, redirect, url_for, flash
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

app = Flask(__name__)
app.secret_key = 'chave_secreta_thay_rh'

app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'postgresql://neondb_owner:npg_UBg0b7YKqLPm@ep-steep-wave-aflx731c-pooler.c-2.us-west-2.aws.neon.tech/neondb?sslmode=require')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

class ItemEstoque(db.Model):
    __tablename__ = 'itens_estoque'
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(100), nullable=False)
    categoria = db.Column(db.String(50))
    tamanho = db.Column(db.String(10))
    quantidade = db.Column(db.Integer, default=0)
    data_atualizacao = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

@app.route('/')
def index():
    itens = ItemEstoque.query.order_by(ItemEstoque.nome).all()
    return render_template('estoque.html', itens=itens)

@app.route('/adicionar', methods=['POST'])
def adicionar():
    nome = request.form.get('nome')
    categoria = request.form.get('categoria')
    tamanho = request.form.get('tamanho')
    quantidade = request.form.get('quantidade')
    
    novo_item = ItemEstoque(nome=nome, categoria=categoria, tamanho=tamanho, quantidade=quantidade)
    db.session.add(novo_item)
    db.session.commit()
    flash('Item adicionado com sucesso!')
    return redirect(url_for('index'))

@app.route('/atualizar/<int:id>', methods=['POST'])
def atualizar(id):
    item = ItemEstoque.query.get_or_404(id)
    operacao = request.form.get('operacao')
    qtd = int(request.form.get('quantidade_mov', 0))
    
    if operacao == 'entrada':
        item.quantidade += qtd
    elif operacao == 'saida':
        item.quantidade -= qtd
        if item.quantidade < 0: item.quantidade = 0
        
    item.data_atualizacao = datetime.utcnow()
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/deletar/<int:id>')
def deletar(id):
    item = ItemEstoque.query.get_or_404(id)
    db.session.delete(item)
    db.session.commit()
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)