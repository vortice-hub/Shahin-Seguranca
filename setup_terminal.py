from app import create_app, db
from app.models import User
import sys

app = create_app()

with app.app_context():
    print("--- Verificando Usuário Terminal ---")
    if not User.query.filter_by(username='terminal').first():
        try:
            terminal = User(
                username='terminal',
                real_name='Terminal de Ponto',
                role='Terminal',
                is_first_access=False,
                cpf='00000000000', 
                salario=0.0
            )
            # Senha padrao para o dispositivo da parede
            terminal.set_password('terminal1234') 
            db.session.add(terminal)
            db.session.commit()
            print(">>> SUCESSO: Usuário 'terminal' criado com a senha 'terminal1234'.")
        except Exception as e:
            print(f">>> ERRO ao criar terminal: {e}")
            # db.session.rollback() # Pode falhar se a sessao nao estiver ativa, o script encerra
    else:
        print(">>> Usuário 'terminal' já existe.")