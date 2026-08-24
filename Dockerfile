FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml README.md ./
COPY src ./src

RUN python -m pip install --disable-pip-version-check --no-cache-dir . \
    && addgroup --system pipeline \
    && adduser --system --ingroup pipeline pipeline \
    && mkdir -p /app/data/raw \
    && chown -R pipeline:pipeline /app

COPY --chown=pipeline:pipeline config ./config

USER pipeline

ENTRYPOINT ["warsaw-property-pipeline"]
CMD ["--help"]
