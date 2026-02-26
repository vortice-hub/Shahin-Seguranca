# Usa a versão do Python que você já definiu no runtime.txt
FROM python:3.11-slim

# Define variáveis para o Python não gerar arquivos .pyc e logs aparecerem direto no console
ENV PYTHONUNBUFFERED True
ENV APP_HOME /app

# --- AQUI ESTÁ O TRUQUE DO FUSO HORÁRIO (BLINDAGEM NÍVEL SO) ---
# Força o servidor a operar no horário de Brasília cravado no Linux
ENV TZ=America/Sao_Paulo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

WORKDIR $APP_HOME

# Instala dependências do sistema (Linux) necessárias para o PostgreSQL, fuso horário
# E PARA A INTELIGÊNCIA ARTIFICIAL (cmake, g++, libgl1)
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    tzdata \
    cmake \
    g++ \
    make \
    libgl1 \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala as bibliotecas do projeto
COPY requirements.txt .
# NOTA: O deploy vai demorar um pouco mais nesta etapa (o dlib será compilado do zero).
RUN pip install --no-cache-dir -r requirements.txt

# Copia todo o código do sistema para dentro do container
COPY . .

# Comando de inicialização (Igual ao seu Procfile)
# O Cloud Run vai injetar a variável $PORT automaticamente
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 run:app

