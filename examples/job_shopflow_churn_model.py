"""
Glue Job: job_shopflow_churn_model
Predicción de churn (abandono de cliente) con Gradient Boosted Trees v2.1.
Features principales: total_orders, days_since_last_order, total_spent, avg_order_value.
risk_level: high (prob > 0.70) / medium (0.40-0.70) / low (< 0.40)

Nota: el modelo se carga desde S3 como artefacto MLflow serializado.
"""
from pyspark.sql import functions as F
from pyspark.ml import PipelineModel
from _spark_builder import get_spark

spark = get_spark("job_shopflow_churn_model")

FACT_PATH    = "s3://shopflow-datalake-prod/analytics/shopflow/fact_sales/"
C360_PATH    = "s3://shopflow-datalake-prod/reports/shopflow/customer_360/"
MODEL_PATH   = "s3://shopflow-datalake-prod/ml/models/churn_gbt_v2.1/"
OUTPUT_PATH  = "s3://shopflow-datalake-prod/ml/shopflow/churn_scores/"
MODEL_VERSION = "2.1"

fact = spark.read.parquet(FACT_PATH)
c360 = spark.read.parquet(C360_PATH)

# Feature engineering
features = (
    c360.withColumn(
        "days_since_last_order",
        F.datediff(F.current_date(), F.col("last_order_date"))
    )
    .select("customer_id", "total_orders", "total_spent",
            "avg_order_value", "days_since_last_order", "year", "month")
)

# Inference: carga modelo preentrenado
model = PipelineModel.load(MODEL_PATH)
predictions = model.transform(features)

scores = (
    predictions
    .withColumnRenamed("probability_churn", "churn_probability")
    .withColumn(
        "risk_level",
        F.when(F.col("churn_probability") > 0.70, "high")
         .when(F.col("churn_probability") > 0.40, "medium")
         .otherwise("low")
    )
    .withColumn("predicted_at", F.current_timestamp())
    .withColumn("model_version", F.lit(MODEL_VERSION))
    .select("customer_id", "churn_probability", "risk_level", "predicted_at", "model_version")
)

scores.write.mode("overwrite").parquet(OUTPUT_PATH)

spark.stop()
