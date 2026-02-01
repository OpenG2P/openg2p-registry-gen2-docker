The single image works because we install both the worker code (celery-workers) and the producer code (celery-beat-producers) into the same Docker image (defined in celery-develop.txt).

Since both codebases are present, we simply tell Docker which application to load at startup using Environment Variables.

In the Dockerfile, the command is dynamic:

dockerfile
CMD celery -A ${CELERY_APP} ${CELERY_OPTS}
You switch modes by passing these environment variables at runtime (e.g., in your helm values.yaml or docker run command):

1. To Run as a Worker (Default)
This is the default behavior if you don't provide any variables.

CELERY_APP: openg2p_registry_celery_workers.main.celery_app
CELERY_OPTS: worker --loglevel=info
2. To Run as a Producer (Beat Scheduler)
Override the variables to point to the producer app and enable the beat flag.

CELERY_APP: openg2p_registry_celery_beat_producers.main.celery_app
CELERY_OPTS: worker --beat --loglevel=info --schedule=/tmp/celery-beat-schedule.db
