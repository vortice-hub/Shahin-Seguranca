# Usa a versão do Python que você já definiu no runtime.txt
FROM python:3.11-slim

# Define variáveis para o Python não gerar arquivos .pyc e logs aparecerem na hora
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app

# --- AQUI ESTÁ O TRUQUE DO FUSO HORÁRIO ---
# Força o servidor a operar no horário de Brasília, eliminando cálculos manuais
ENV TZ=America/Sao_Paulo

WORKDIR $APP_HOME

# Instala dependências do sistema (Linux) necessárias para o PostgreSQL e PDF
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    tzdata \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala as bibliotecas do seu projeto
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do Shahin para dentro do container
COPY . .

# Comando de inicialização (Igual ao seu Procfile)
# O Cloud Run vai injetar a variável $PORT automaticamente
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 run:app