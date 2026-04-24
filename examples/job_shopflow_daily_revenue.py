"""
Glue Job: job_shopflow_daily_revenue
Genera el informe diario de ingresos por país y segmento de cliente.
Usado por el equipo de Revenue Operations cada mañana en el dashboard de BI.
KPIs: total_orders, total_revenue, avg_order_value
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_daily_revenue")

INPUT_PATH  = "s3://shopflow-datalake-prod/analytics/shopflow/fact_sales/"
OUTPUT_PATH = "s3://shopflow-datalake-prod/reports/shopflow/daily_revenue/"

fact = spark.read.parquet(INPUT_PATH)

report = (
    fact.groupBy("order_date", "country", "segment", "year", "month")
        .agg(
            F.countDistinct("order_id").alias("total_orders"),
            F.sum("amount").alias("total_revenue"),
            F.avg("amount").alias("avg_order_value"),
        )
        .withColumnRenamed("order_date", "report_date")
)

report.write \
    .mode("overwrite") \
    .partitionBy("year", "month") \
    .parquet(OUTPUT_PATH)

spark.stop()
