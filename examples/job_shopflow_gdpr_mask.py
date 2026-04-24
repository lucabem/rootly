"""
Glue Job: job_shopflow_gdpr_mask
Anonimiza datos de clientes para cumplimiento GDPR (Art. 17 - Derecho al olvido).
ELIMINA: name, email, phone (PII directa identificable)
CONSERVA: customer_id (seudónimo), signup_date, segment, country, age_days

El dataset de salida es apto para análisis con terceros y audit trails regulatorios.
"""
from _spark_builder import get_spark

spark = get_spark("job_shopflow_gdpr_mask")

INPUT_PATH  = "s3://shopflow-datalake-prod/staging/shopflow/customers_enriched/"
OUTPUT_PATH = "s3://shopflow-datalake-prod/compliance/shopflow/customers_anonymized/"

# Columnas PII que se eliminan explícitamente — NO propagar downstream
PII_COLUMNS = ["name", "email", "phone"]

df = spark.read.parquet(INPUT_PATH)

df_anon = df.drop(*PII_COLUMNS).select(
    "customer_id", "signup_date", "segment", "country", "age_days"
)

df_anon.write.mode("overwrite").parquet(OUTPUT_PATH)

spark.stop()
