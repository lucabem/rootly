# Java 17 ya incluido; Ubuntu 22.04 (jammy)
FROM eclipse-temurin:17-jdk-jammy

# ── Python 3 + pip ────────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-pip curl procps \
    && ln -s /usr/bin/python3 /usr/local/bin/python \
    && rm -rf /var/lib/apt/lists/*

# ── Dependencias Python (pyspark incluye los binarios de Spark) ───────────────
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# ── Pre-descarga del JAR de OpenLineage en build time ─────────────────────────
ENV PACKAGES="io.openlineage:openlineage-spark_2.12:1.43.0"

RUN python -c "\
from pyspark.sql import SparkSession; \
SparkSession.builder \
  .config('spark.jars.packages', '${PACKAGES}') \
  .config('spark.jars.ivy', '/root/.ivy2') \
  .master('local') \
  .getOrCreate() \
  .stop()" 2>/dev/null || true

# ── Código fuente ──────────────────────────────────────────────────────────────
WORKDIR /app
COPY . /app/

RUN mkdir -p /app/openlineage
