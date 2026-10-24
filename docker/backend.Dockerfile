FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Las dependencias se instalan antes de copiar el código para que un cambio en
# el código no invalide la capa de dependencias.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY simulation ./simulation
COPY backend ./backend
COPY data ./data
# Los scripts operativos viven con la API porque necesitan su conexión a la
# base: importar el gazetteer mundial o sembrar una demostración se hacen con
# `docker compose exec api python scripts/...`.
COPY scripts ./scripts

ENV PYTHONPATH=/app:/app/backend

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
