"""
Glue Job: job_shopflow_sales_fact
Construye la tabla de hechos de ventas uniendo pedidos limpios con clientes enriquecidos.
- Join: orders_clean.customer_id = customers_enriched.customer_id
- Genera sale_id sintético con prefijo SF- para trazabilidad cross-sistema
- Propaga segment y ltv_segment del cliente para análisis segmentado
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_sales_fact")

ORDERS_PATH    = "s3://shopflow-datalake-prod/staging/shopflow/orders_clean/"
CUSTOMERS_PATH = "s3://shopflow-datalake-prod/staging/shopflow/customers_enriched/"
OUTPUT_PATH    = "s3://shopflow-datalake-prod/analytics/shopflow/fact_sales/"

orders    = spark.read.parquet(ORDERS_PATH)
customers = spark.read.parquet(CUSTOMERS_PATH).select(
    "customer_id", "segment", "ltv_segment"
)

fact = (
    orders.join(customers, on="customer_id", how="left")
          .withColumn("sale_id", F.concat(F.lit("SF-"), F.col("order_id")))
          .select(
              "sale_id", "order_id", "customer_id", "product_id",
              "amount", "quantity", "order_date",
              "segment", "ltv_segment", "country", "year", "month"
          )
)

fact.write \
    .mode("overwrite") \
    .partitionBy("year", "month") \
    .parquet(OUTPUT_PATH)

spark.stop()
