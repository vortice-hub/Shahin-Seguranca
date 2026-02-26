# 1. PUXA A SUA IMAGEM BASE (Pronta e compilada)
FROM gcr.io/nimble-gearing-487415-u6/vortice-base:latest

ENV APP_HOME /app
WORKDIR $APP_HOME

# 2. Instala apenas as bibliotecas leves do requirements.txt
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 3. Copia o código do seu sistema (Rotas, HTML, etc)
COPY . .

# 4. Inicializa o servidor no Cloud Run
CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 run:app

