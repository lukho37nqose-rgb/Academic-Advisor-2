FROM python:3.14-slim@sha256:cea0e6040540fb2b965b6e7fb5ffa00871e632eef63719f0ea54bca189ce14a6

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV IRE_AUTO_CREATE_SCHEMA=false

WORKDIR /app

COPY requirements.txt /app/
RUN pip install --no-cache-dir --require-hashes -r requirements.txt \
    && pip check

RUN addgroup --system ire && adduser --system --ingroup ire ire
COPY --chown=ire:ire . /app/
USER ire

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health/live', timeout=3)" || exit 1

CMD ["uvicorn", "app.api:app", "--host", "0.0.0.0", "--port", "8000"]
