"""
01_hudi_to_iceberg.py
---------------------
Reads the Hudi `orders` table and writes the result of an aggregation SQL
to an Iceberg table `order_stats`.

Local:
    python examples/01_hudi_to_iceberg.py

Docker:
    docker compose run --rm spark python examples/01_hudi_to_iceberg.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _spark_builder import BASE_DIR, build_spark

HUDI_ORDERS = os.path.join(BASE_DIR, "data", "hudi", "orders")
APP_NAME = "hudi_to_iceberg_order_stats"


def main() -> None:
    spark = build_spark(APP_NAME)
    spark.sparkContext.setLogLevel("WARN")

    # 1. Read Hudi table
    print(f"[1/3] Reading Hudi table from {HUDI_ORDERS}")
    orders = spark.read.format("hudi").load(HUDI_ORDERS)
    orders.createOrReplaceTempView("orders")
    print(f"      {orders.count()} orders loaded")

    # 2. Aggregation SQL
    print("[2/3] Running aggregation SQL...")
    result = spark.sql(
        """
        SELECT
            customer_id,
            status,
            COUNT(*)                        AS order_count,
            ROUND(SUM(amount), 2)           AS total_amount,
            ROUND(AVG(amount), 2)           AS avg_amount,
            MIN(created_at)                 AS first_order_at,
            MAX(created_at)                 AS last_order_at
        FROM orders
        GROUP BY customer_id, status
        ORDER BY total_amount DESC
    """
    )
    result.show(10, truncate=False)

    # 3. Write to Iceberg
    print("[3/3] Writing Iceberg table -> local.poc.order_stats")
    (
        result.writeTo("local.poc.order_stats")
        .tableProperty("write.format.default", "parquet")
        .createOrReplace()
    )
    print("[OK] Done.")
    spark.stop()


if __name__ == "__main__":
    main()
