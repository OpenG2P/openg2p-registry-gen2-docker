FROM python:3.12.11-alpine3.22

RUN apk add --no-cache --virtual .build-deps gcc libc-dev linux-headers make \
 && apk add --no-cache bash git gettext libpq-dev libffi-dev openssl-dev

WORKDIR /app

# Install dependencies from the generated requirements file
COPY adapters.requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

RUN apk del --no-network .build-deps

ENV PYTHONUNBUFFERED=1
ENV CELERY_APP=openg2p_registry_celery_workers.main.celery_app
ENV CELERY_OPTS="worker --loglevel=info"

# Default command uses env vars to allow flexibility (worker vs beat)
CMD celery -A ${CELERY_APP} ${CELERY_OPTS}
