FROM python:3.11-slim

ARG GIT_COMMIT=dev
ARG GIT_DATE=
ENV GIT_COMMIT=${GIT_COMMIT}
ENV GIT_DATE=${GIT_DATE}

WORKDIR /app

COPY pyproject.toml .
COPY app/ app/
COPY config/ config/
COPY data/ data/
COPY scripts/ scripts/

RUN pip install .

COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

ENTRYPOINT ["./docker-entrypoint.sh"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
