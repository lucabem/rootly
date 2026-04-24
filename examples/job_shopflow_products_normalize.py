"""
Glue Job: job_shopflow_products_normalize
Normaliza el catálogo de productos del ERP.
- category_code: versión estandarizada de category (UPPER + guiones bajos)
- Descarta productos sin SKU o precio nulo
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_products_normalize")

INPUT_PATH  = "s3://shopflow-datalake-prod/raw/shopflow/products/"
OUTPUT_PATH = "s3://shopflow-datalake-prod/staging/shopflow/products_normalized/"

df = spark.read.parquet(INPUT_PATH)

df_norm = (
    df.filter(F.col("sku").isNotNull() & F.col("price").isNotNull() & (F.col("price") > 0))
      .withColumn(
          "category_code",
          F.upper(F.regexp_replace(F.trim(F.col("category")), r"\s+", "_"))
      )
      .withColumn("fecha_carga", F.current_timestamp())
)

df_norm.write.mode("overwrite").parquet(OUTPUT_PATH)

spark.stop()
