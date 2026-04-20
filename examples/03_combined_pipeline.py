"""
03_combined_pipeline.py
-----------------------
Full pipeline: Hudi + Delta -> JOIN SQL -> Iceberg (sales_summary).

OpenLineage records two inputs and one output, producing the most
interesting lineage graph in this POC.

Local:
    python examples/03_combined_pipeline.py

Docker:
    docker compose run --rm spark python examples/03_combined_pipeline.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))
from _spark_builder import BASE_DIR, build_spark

HUDI_ORDERS = os.path.join(BASE_DIR, "data", "hudi", "orders")
DELTA_CUSTOMERS = os.path.join(BASE_DIR, "data", "delta", "customers")
APP_NAME = "combined_pipeline_sales_summary"


def main() -> None:
    spark = build_spark(APP_NAME)
    spark.sparkContext.setLogLevel("WARN")

    # 1. Read sources
    print(f"[1/4] Reading Hudi table  -> {HUDI_ORDERS}")
    orders = spark.read.format("hudi").load(HUDI_ORDERS)
    orders.createOrReplaceTempView("orders")
    print(f"      {orders.count()} orders")

    print(f"[2/4] Reading Delta table -> {DELTA_CUSTOMERS}")
    customers = spark.read.format("delta").load(DELTA_CUSTOMERS)
    customers.createOrReplaceTempView("customers")
    print(f"      {customers.count()} customers")

    # 2. JOIN + aggregation SQL
    print("[3/4] Running join and aggregation SQL...")
    result = spark.sql(
        """
        SELECT
            c.customer_id,
            c.name                                          AS customer_name,
            c.country,
            CASE
                WHEN c.country IN ('ES', 'FR', 'DE') THEN 'EMEA'
                WHEN c.country IN ('MX', 'AR', 'CO', 'PE', 'CL', 'BR') THEN 'LATAM'
                WHEN c.country = 'US' THEN 'AMER'
                ELSE 'OTHER'
            END                                             AS region,
            COUNT(o.order_id)                               AS total_orders,
            COUNT(CASE WHEN o.status = 'delivered'  THEN 1 END) AS delivered_orders,
            COUNT(CASE WHEN o.status = 'cancelled'  THEN 1 END) AS cancelled_orders,
            ROUND(SUM(o.amount), 2)                         AS total_revenue,
            ROUND(AVG(o.amount), 2)                         AS avg_order_value,
            ROUND(
                COUNT(CASE WHEN o.status = 'delivered' THEN 1 END) * 100.0
                / NULLIF(COUNT(o.order_id), 0), 1
            )                                               AS delivery_rate_pct,
            MAX(o.created_at)                               AS last_order_at
        FROM customers c
        LEFT JOIN orders o USING (customer_id)
        GROUP BY c.customer_id, c.name, c.country
        ORDER BY total_revenue DESC NULLS LAST
    """
    )
    result.show(10, truncate=False)
    print(f"      {result.count()} rows in result")

    # 3. Write to Iceberg
    print("[4/4] Writing Iceberg table -> local.poc.sales_summary")
    (
        result.writeTo("local.poc.sales_summary")
        .tableProperty("write.format.default", "parquet")
        .tableProperty("write.metadata.compression-codec", "gzip")
        .createOrReplace()
    )

    print("[OK] Done.")
    spark.stop()


if __name__ == "__main__":
    main()
