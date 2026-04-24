import os
from pyspark.sql import SparkSession

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EVENTS_FILE = os.path.join(_ROOT, "openlineage", "events.ndjson")


def get_spark(job_name: str) -> SparkSession:
    os.makedirs(os.path.dirname(EVENTS_FILE), exist_ok=True)
    return (
        SparkSession.builder
        .appName(job_name)
        .config("spark.jars.packages", "io.openlineage:openlineage-spark_2.12:1.43.0")
        .config("spark.extraListeners", "io.openlineage.spark.agent.OpenLineageSparkListener")
        .config("spark.openlineage.namespace", "shopflow")
        .config("spark.openlineage.transport.type", "file")
        .config("spark.openlineage.transport.location", EVENTS_FILE)
        .getOrCreate()
    )
