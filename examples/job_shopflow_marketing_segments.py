"""
Glue Job: job_shopflow_marketing_segments
Asigna acción de marketing a cada cliente cruzando su perfil 360 con el riesgo de churn.
- recommended_action: retention_call (alto riesgo) | discount_email (medio) | upsell_push (bajo)
- campaign_code: código de integración con la plataforma de email marketing (Braze)
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_marketing_segments")

C360_PATH   = "s3://shopflow-datalake-prod/reports/shopflow/customer_360/"
CHURN_PATH  = "s3://shopflow-datalake-prod/ml/shopflow/churn_scores/"
OUTPUT_PATH = "s3://shopflow-datalake-prod/reports/shopflow/marketing_segments/"

c360  = spark.read.parquet(C360_PATH)
churn = spark.read.parquet(CHURN_PATH).select("customer_id", "risk_level")

joined = c360.join(churn, on="customer_id", how="left")

segments = (
    joined
    .withColumn(
        "recommended_action",
        F.when(F.col("risk_level") == "high",   "retention_call")
         .when(F.col("risk_level") == "medium",  "discount_email")
         .otherwise("upsell_push")
    )
    .withColumn(
        "campaign_code",
        F.concat_ws("_", F.col("risk_level"), F.col("year"), F.col("month"))
    )
    .select(
        "customer_id",
        F.coalesce(F.col("risk_level"), F.lit("unknown")).alias("churn_risk"),
        "recommended_action", "campaign_code"
    )
)

segments.write.mode("overwrite").parquet(OUTPUT_PATH)

spark.stop()
