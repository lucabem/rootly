"""
Glue Job: job_shopflow_product_metrics
Agrega métricas de rendimiento de producto por mes.
- total_sold:    SUM(quantity) por product_id, year, month
- total_revenue: SUM(amount)   por product_id, year, month
- avg_price:     precio medio efectivo de venta (≠ precio de catálogo)
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_product_metrics")

ORDERS_PATH   = "s3://shopflow-datalake-prod/staging/shopflow/orders_clean/"
PRODUCTS_PATH = "s3://shopflow-datalake-prod/staging/shopflow/products_normalized/"
OUTPUT_PATH   = "s3://shopflow-datalake-prod/analytics/shopflow/product_metrics/"

orders   = spark.read.parquet(ORDERS_PATH)
products = spark.read.parquet(PRODUCTS_PATH).select(
    "product_id", "sku", "name", "category"
)

metrics = (
    orders.join(products, on="product_id", how="inner")
          .groupBy("product_id", "sku", "name", "category", "year", "month")
          .agg(
              F.sum("quantity").alias("total_sold"),
              F.sum("amount").alias("total_revenue"),
              (F.sum("amount") / F.sum("quantity")).alias("avg_price"),
          )
)

metrics.write \
    .mode("overwrite") \
    .partitionBy("year", "month") \
    .parquet(OUTPUT_PATH)

spark.stop()
