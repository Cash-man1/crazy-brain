# Immagine ufficiale Playwright + Python (include Chromium e dipendenze sistema).
# Build su Render: imposta "Root Directory" = backend (oppure usa render.yaml con dockerContext).
FROM mcr.microsoft.com/playwright/python:v1.52.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Allinea browser alla versione del pacchetto (l'immagine è già allineata a 1.52.x).
RUN playwright install --with-deps chromium

COPY . .

# Render inietta PORT (es. 10000).
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000}"]
