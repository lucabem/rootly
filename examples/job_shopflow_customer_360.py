"""
Glue Job: job_shopflow_customer_360
Vista 360º de cada cliente: historial de compras, gasto total y categoría favorita.
- favorite_category: categoría con mayor volumen de unidades compradas (moda)
- Usado por los equipos de CRM, personalización y marketing
"""
from pyspark.sql import functions as F
from pyspark.sql.window import Window
from _spark_builder import get_spark

spark = get_spark("job_shopflow_customer_360")

FACT_PATH    = "s3://shopflow-datalake-prod/analytics/shopflow/fact_sales/"
METRICS_PATH = "s3://shopflow-datalake-prod/analytics/shopflow/product_metrics/"
OUTPUT_PATH  = "s3://shopflow-datalake-prod/reports/shopflow/customer_360/"

fact    = spark.read.parquet(FACT_PATH)
metrics = spark.read.parquet(METRICS_PATH).select("product_id", "category")

# Categoría favorita: la que más unidades ha comprado el cliente
fact_with_cat = fact.join(metrics, on="product_id", how="left")

w_cat = Window.partitionBy("customer_id", "year", "month").orderBy(F.desc("cat_qty"))
cat_rank = (
    fact_with_cat.groupBy("customer_id", "category", "year", "month")
                 .agg(F.sum("quantity").alias("cat_qty"))
                 .withColumn("rn", F.row_number().over(w_cat))
                 .filter(F.col("rn") == 1)
                 .select("customer_id", F.col("category").alias("favorite_category"), "year", "month")
)

base = (
    fact.groupBy("customer_id", "year", "month")
        .agg(
            F.countDistinct("order_id").alias("total_orders"),
            F.sum("amount").alias("total_spent"),
            F.max("order_date").alias("last_order_date"),
            F.avg("amount").alias("avg_order_value"),
        )
)

c360 = base.join(cat_rank, on=["customer_id", "year", "month"], how="left")

c360.write \
    .mode("overwrite") \
    .partitionBy("year", "month") \
    .parquet(OUTPUT_PATH)

spark.stop()
