from app import create_app

# Cria a aplicação usando a fábrica
app = create_app()

if __name__ == "__main__":
    # Roda localmente
    app.run(debug=True)