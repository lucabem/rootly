import os

from celery import Celery
from dotenv import load_dotenv

load_dotenv()

S3_BUCKET = os.getenv("S3_BUCKET")
S3_EVENTS_PREFIX = os.getenv("S3_EVENTS_PREFIX", "openlineage/")
S3_JOBS_PREFIX = os.getenv("S3_JOBS_PREFIX", "code/glue/jobs/AEMET/")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")

celery_app = Celery("tasks", broker=REDIS_URL, backend=REDIS_URL)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
)


@celery_app.task(bind=True)
def run_sync_task(self, bucket, events_prefix, jobs_prefix):
    from rag.query import sync as rag_sync

    G, collection = rag_sync(
        bucket=bucket,
        events_prefix=events_prefix,
        jobs_prefix=jobs_prefix,
    )
    n_ds = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "dataset")
    n_job = sum(1 for _, d in G.nodes(data=True) if d.get("kind") == "job")
    return {
        "docs": collection.count(),
        "datasets": n_ds,
        "jobs": n_job,
        "source": f"s3://{bucket}/{events_prefix}" if bucket else "local",
    }
