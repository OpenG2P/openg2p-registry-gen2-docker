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
ENV STAFF_PORTAL_WORKER_TYPE=gunicorn
ENV STAFF_PORTAL_HOST=0.0.0.0
ENV STAFF_PORTAL_PORT=8000
ENV STAFF_PORTAL_NO_OF_WORKERS=8

# Use module path for migrate and Gunicorn WSGI app
CMD python3 -m openg2p_registry_staff_portal_api.main migrate; \
    ${STAFF_PORTAL_WORKER_TYPE} "openg2p_registry_staff_portal_api.main:app" --workers ${STAFF_PORTAL_NO_OF_WORKERS} --worker-class uvicorn.workers.UvicornWorker --bind ${STAFF_PORTAL_HOST}:${STAFF_PORTAL_PORT}
