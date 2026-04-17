"""
02_delta_to_iceberg.py
----------------------
Lee la tabla Delta `customers` y escribe una vista enriquecida
a una tabla Iceberg `customer_profiles`.

Uso local:
    python examples/02_delta_to_iceberg.py

Uso Docker:
    docker compose run --rm spark python examples/02_delta_to_iceberg.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _spark_builder import BASE_DIR, build_spark

DELTA_CUSTOMERS = os.path.join(BASE_DIR, "data", "delta", "customers")
APP_NAME        = "delta_to_iceberg_customer_profiles"


def main() -> None:
    spark = build_spark(APP_NAME)
    spark.sparkContext.setLogLevel("WARN")

    # ── 1. Leer tabla Delta ────────────────────────────────────────────────────
    print(f"[1/3] Leyendo tabla Delta desde {DELTA_CUSTOMERS}")
    customers = spark.read.format("delta").load(DELTA_CUSTOMERS)
    customers.createOrReplaceTempView("customers")
    print(f"      {customers.count()} clientes cargados")

    # ── 2. SQL de transformación ───────────────────────────────────────────────
    print("[2/3] Ejecutando SQL de enriquecimiento...")
    result = spark.sql("""
        SELECT
            customer_id,
            name,
            email,
            country,
            signup_date,
            CASE
                WHEN country IN ('ES', 'FR', 'DE') THEN 'EMEA'
                WHEN country IN ('MX', 'AR', 'CO', 'PE', 'CL', 'BR') THEN 'LATAM'
                WHEN country = 'US' THEN 'AMER'
                ELSE 'OTHER'
            END                                         AS region,
            YEAR(CAST(signup_date AS DATE))             AS signup_year,
            MONTH(CAST(signup_date AS DATE))            AS signup_month
        FROM customers
        ORDER BY region, country, customer_id
    """)
    result.show(10, truncate=False)

    # ── 3. Escribir en Iceberg ─────────────────────────────────────────────────
    print("[3/3] Escribiendo tabla Iceberg → local.poc.customer_profiles")
    (
        result.writeTo("local.poc.customer_profiles")
        .tableProperty("write.format.default", "parquet")
        .tableProperty("write.metadata.compression-codec", "gzip")
        .createOrReplace()
    )
    print("[OK] Listo.")
    spark.stop()


if __name__ == "__main__":
    main()
