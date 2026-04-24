"""
Glue Job: job_shopflow_customers_enrich
Enriquece el maestro de clientes del CRM con métricas calculadas.
- age_days: días desde signup_date hasta hoy
- ltv_segment: clasificación de valor de vida (high/medium/low) basada en segment
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_customers_enrich")

INPUT_PATH  = "s3://shopflow-datalake-prod/raw/shopflow/customers/"
OUTPUT_PATH = "s3://shopflow-datalake-prod/staging/shopflow/customers_enriched/"

df = spark.read.parquet(INPUT_PATH)

df_enriched = (
    df.withColumn(
        "age_days",
        F.datediff(F.current_date(), F.col("signup_date"))
    )
    .withColumn(
        "ltv_segment",
        F.when(F.col("segment") == "premium", "high")
         .when(F.col("segment") == "standard", "medium")
         .otherwise("low")
    )
    .withColumn("fecha_carga", F.current_timestamp())
    # Conserva email y phone en staging; se eliminan en el job GDPR downstream
    .select(
        "customer_id", "name", "email", "signup_date",
        "segment", "country", "age_days", "ltv_segment", "fecha_carga"
    )
)

df_enriched.write.mode("overwrite").parquet(OUTPUT_PATH)

spark.stop()
