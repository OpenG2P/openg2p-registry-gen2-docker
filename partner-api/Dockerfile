FROM python:3.12.11-alpine3.22

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libmagic

WORKDIR /app

# Copy local package sources (may be empty for remote-only builds)
COPY local_deps/ /app/local_deps/

# Install dependencies from the generated requirements file
COPY adapters.requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1
ENV PARTNER_WORKER_TYPE=gunicorn
ENV PARTNER_HOST=0.0.0.0
ENV PARTNER_PORT=8000
ENV PARTNER_NO_OF_WORKERS=8

# Use module path for migrate and Gunicorn WSGI app
CMD python3 -m openg2p_registry_partner_api.main migrate; \
    ${PARTNER_WORKER_TYPE} "openg2p_registry_partner_api.main:app" --workers ${PARTNER_NO_OF_WORKERS} --worker-class uvicorn.workers.UvicornWorker --bind ${PARTNER_HOST}:${PARTNER_PORT}
