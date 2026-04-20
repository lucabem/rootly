"""
02_delta_to_iceberg.py
----------------------
Reads the Delta `customers` table and writes an enriched view
to an Iceberg table `customer_profiles`.

Local:
    python examples/02_delta_to_iceberg.py

Docker:
    docker compose run --rm spark python examples/02_delta_to_iceberg.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _spark_builder import BASE_DIR, build_spark

DELTA_CUSTOMERS = os.path.join(BASE_DIR, "data", "delta", "customers")
APP_NAME = "delta_to_iceberg_customer_profiles"


def main() -> None:
    spark = build_spark(APP_NAME)
    spark.sparkContext.setLogLevel("WARN")

    # 1. Read Delta table
    print(f"[1/3] Reading Delta table from {DELTA_CUSTOMERS}")
    customers = spark.read.format("delta").load(DELTA_CUSTOMERS)
    customers.createOrReplaceTempView("customers")
    print(f"      {customers.count()} customers loaded")

    # 2. Enrichment SQL
    print("[2/3] Running enrichment SQL...")
    result = spark.sql(
        """
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
    """
    )
    result.show(10, truncate=False)

    # ── 3. Write to Iceberg ───────────────────────────────────────────────────
    print("[3/3] Writing Iceberg table -> local.poc.customer_profiles")
    (
        result.writeTo("local.poc.customer_profiles")
        .tableProperty("write.format.default", "parquet")
        .tableProperty("write.metadata.compression-codec", "gzip")
        .createOrReplace()
    )
    print("[OK] Done.")
    spark.stop()


if __name__ == "__main__":
    main()
