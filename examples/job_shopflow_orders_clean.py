"""
Glue Job: job_shopflow_orders_clean
Limpia y particiona los pedidos raw llegados del OMS.
- Descarta pedidos con status CANCELLED o NULL
- Normaliza country a ISO-2 en mayúsculas
- Extrae year/month de order_date para particionado S3
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_orders_clean")

INPUT_PATH  = "s3://shopflow-datalake-prod/raw/shopflow/orders/"
OUTPUT_PATH = "s3://shopflow-datalake-prod/staging/shopflow/orders_clean/"

df = spark.read.parquet(INPUT_PATH)

df_clean = (
    df.filter(F.col("status").isNotNull() & (F.col("status") != "CANCELLED"))
      .filter(F.col("amount") > 0)
      .withColumn("country", F.upper(F.trim(F.col("country"))))
      .withColumn("year",  F.year(F.col("order_date")).cast("string"))
      .withColumn("month", F.lpad(F.month(F.col("order_date")).cast("string"), 2, "0"))
      .withColumn("fecha_carga", F.current_timestamp())
)

df_clean.write \
    .mode("overwrite") \
    .partitionBy("year", "month") \
    .parquet(OUTPUT_PATH)

spark.stop()
