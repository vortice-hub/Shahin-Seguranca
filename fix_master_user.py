from app import create_app, db
from app.models import User

app = create_app()

with app.app_context():
    print("--- Corrigindo Usuario Thaynara ---")
    user = User.query.filter_by(username='Thaynara').first()
    
    if user:
        user.role = 'Master'
        user.set_password('1855')
        db.session.commit()
        print(">>> SUCESSO: Thaynara agora é Master com senha '1855'.")
    else:
        # Se nao existir, cria
        novo = User(
            username='Thaynara',
            real_name='Thaynara Master',
            role='Master',
            is_first_access=False,
            cpf='00000000001', # CPF Ficticio Master
            salario=0.0
        )
        novo.set_password('1855')
        db.session.add(novo)
        db.session.commit()
        print(">>> SUCESSO: Usuario Thaynara CRIADO.")