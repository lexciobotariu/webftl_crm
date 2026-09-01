FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# collectstatic must run with DEBUG=False so it writes the hashed-filename
# manifest that WhiteNoise needs at runtime; settings then demand SECRET_KEY and
# FERNET_KEY. These build-only values are scoped to this RUN and never reach the
# running container — supply real ones as environment variables at run time.
RUN SECRET_KEY=build-only-not-a-runtime-secret \
    FERNET_KEY=Rl6h1L1_2sVN9m8Kk2vTQaXVBUOzOOoTGKqZfE9vGxA= \
    DEBUG=False \
    SECURE_SSL_REDIRECT=False \
    python manage.py collectstatic --noinput

# Run as an unprivileged user.
RUN useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", \
     "--bind", "0.0.0.0:8000", \
     "--workers", "3", \
     "--timeout", "60", \
     "--access-logfile", "-"]
