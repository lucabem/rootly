"""
Glue Job: job_shopflow_inventory_forecast
Predicción de demanda de producto para los próximos 30 días (LSTM v1.4).
- predicted_demand:  unidades previstas
- confidence:        probabilidad del intervalo de predicción
- recommended_stock: predicted_demand * 1.15 (margen de seguridad 15%)

El modelo se entrena mensualmente offline; aquí solo se realiza inferencia batch.
"""
from pyspark.sql import functions as F
from pyspark.ml import PipelineModel
from _spark_builder import get_spark

spark = get_spark("job_shopflow_inventory_forecast")

METRICS_PATH  = "s3://shopflow-datalake-prod/analytics/shopflow/product_metrics/"
MODEL_PATH    = "s3://shopflow-datalake-prod/ml/models/demand_lstm_v1.4/"
OUTPUT_PATH   = "s3://shopflow-datalake-prod/ml/shopflow/inventory_forecast/"
SAFETY_MARGIN = 1.15
MODEL_VERSION = "1.4"

metrics = spark.read.parquet(METRICS_PATH)

# Feature engineering: media móvil de los últimos 3 meses como input al modelo
from pyspark.sql.window import Window
w3m = Window.partitionBy("product_id").orderBy("year", "month").rowsBetween(-2, 0)

features = metrics.withColumn("rolling_avg_sold", F.avg("total_sold").over(w3m))

model = PipelineModel.load(MODEL_PATH)
predictions = model.transform(features)

forecast = (
    predictions
    .withColumn("forecast_date", F.date_add(F.current_date(), 30))
    .withColumn("recommended_stock",
                (F.col("predicted_demand") * F.lit(SAFETY_MARGIN)).cast("integer"))
    .select(
        "product_id", "sku", "forecast_date",
        "predicted_demand", "confidence", "recommended_stock"
    )
)

forecast.write.mode("overwrite").parquet(OUTPUT_PATH)

spark.stop()
