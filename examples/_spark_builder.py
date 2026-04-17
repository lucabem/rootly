"""
_spark_builder.py
-----------------
Helper compartido por los scripts de examples/.

Detecta si existe la variable de entorno OPENLINEAGE_URL (inyectada por Docker)
y elige el transporte HTTP; si no, usa transporte file al path local.
"""

import os
from pyspark.sql import SparkSession

BASE_DIR   = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICEBERG_WH = os.path.join(BASE_DIR, "openlineage", "data", "iceberg")

PACKAGES = ",".join([
    "org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0",
    "io.delta:delta-spark_2.12:3.2.0",
    "org.apache.iceberg:iceberg-spark-runtime-3.5_2.12:1.6.1",
    "io.openlineage:openlineage-spark_2.12:1.43.0",
])


def _ol_transport_config(builder: SparkSession.Builder, app_name: str) -> SparkSession.Builder:
    """Configura el transporte OpenLineage según el entorno."""
    ol_url       = os.getenv("OPENLINEAGE_URL")
    ol_namespace = os.getenv("OPENLINEAGE_NAMESPACE", "poc-openlineage")

    builder = (
        builder
        .config("spark.extraListeners",
                "io.openlineage.spark.agent.OpenLineageSparkListener")
        .config("spark.openlineage.namespace", ol_namespace)
        .config("spark.openlineage.appName", app_name)
    )

    events_file = os.path.join(BASE_DIR, "openlineage", "events.ndjson")

    if ol_url:
        print(f"[OL] Transporte HTTP → {ol_url}  +  file → {events_file}")
        builder = (
            builder
            .config("spark.openlineage.transport.type", "composite")
            .config("spark.openlineage.transport.transports.marquez.type", "http")
            .config("spark.openlineage.transport.transports.marquez.url",  ol_url)
            .config("spark.openlineage.transport.transports.file.type", "file")
            .config("spark.openlineage.transport.transports.file.location", events_file)
        )
    else:
        print(f"[OL] Transporte file → {events_file}")
        builder = (
            builder
            .config("spark.openlineage.transport.type", "file")
            .config("spark.openlineage.transport.location", events_file)
        )

    return builder


def build_spark(app_name: str, extra_extensions: list[str] | None = None) -> SparkSession:
    """
    Construye una SparkSession con soporte para Hudi + Delta + Iceberg + OpenLineage.

    extra_extensions: extensiones SQL adicionales si el script sólo necesita un subconjunto.
    """
    base_extensions = [
        "org.apache.spark.sql.hudi.HoodieSparkSessionExtension",
        "io.delta.sql.DeltaSparkSessionExtension",
        "org.apache.iceberg.spark.extensions.IcebergSparkSessionExtensions",
    ]
    extensions = ",".join(base_extensions + (extra_extensions or []))

    ivy_dir = os.getenv("IVY_CACHE", os.path.expanduser("~/.ivy2"))

    # Silencia el WARN de reflexión ilegal de OpenLineage con Java 17
    java17_opens = " ".join([
        "--add-opens=java.base/java.security=ALL-UNNAMED",
        "--add-opens=java.base/sun.nio.ch=ALL-UNNAMED",
        "--add-opens=java.base/java.nio=ALL-UNNAMED",
        "--add-opens=java.base/java.lang=ALL-UNNAMED",
    ])

    builder = (
        SparkSession.builder
        .appName(app_name)
        .master("local[*]")
        .config("spark.jars.packages", PACKAGES)
        .config("spark.jars.ivy", ivy_dir)
        .config("spark.jars.repositories",
                "https://repo1.maven.org/maven2,"
                "https://repository.apache.org/content/repositories/releases")
        .config("spark.driver.extraJavaOptions",   java17_opens)
        .config("spark.executor.extraJavaOptions", java17_opens)

        # ── Hudi ──────────────────────────────────────────────────────────────
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")

        # ── SQL extensions ─────────────────────────────────────────────────────
        .config("spark.sql.extensions", extensions)

        # Hudi como catalog por defecto de spark_catalog
        .config("spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.hudi.catalog.HoodieCatalog")

        # ── Iceberg catalog "local" ────────────────────────────────────────────
        .config("spark.sql.catalog.local",
                "org.apache.iceberg.spark.SparkCatalog")
        .config("spark.sql.catalog.local.type", "hadoop")
        .config("spark.sql.catalog.local.warehouse", ICEBERG_WH)
    )

    builder = _ol_transport_config(builder, app_name)
    return builder.getOrCreate()
