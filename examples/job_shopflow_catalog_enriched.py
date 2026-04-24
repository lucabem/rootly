"""
Glue Job: job_shopflow_catalog_enriched
Enriquece el catálogo de productos con predicciones de inventario para alertas de compras.
- stock_status: ok | understocked | overstocked según stock actual vs demanda prevista
  * understocked: stock < predicted_demand  → alerta urgente a equipo de compras
  * overstocked:  stock > recommended_stock * 2 → riesgo de obsolescencia
"""
from pyspark.sql import functions as F
from _spark_builder import get_spark

spark = get_spark("job_shopflow_catalog_enriched")

PRODUCTS_PATH  = "s3://shopflow-datalake-prod/staging/shopflow/products_normalized/"
FORECAST_PATH  = "s3://shopflow-datalake-prod/ml/shopflow/inventory_forecast/"
OUTPUT_PATH    = "s3://shopflow-datalake-prod/staging/shopflow/catalog_enriched/"

products = spark.read.parquet(PRODUCTS_PATH)
forecast = spark.read.parquet(FORECAST_PATH).select(
    "product_id", "predicted_demand", "recommended_stock"
)

catalog = (
    products.join(forecast, on="product_id", how="left")
            .withColumn(
                "stock_status",
                F.when(F.col("stock") < F.col("predicted_demand"), "understocked")
                 .when(F.col("stock") > F.col("recommended_stock") * 2, "overstocked")
                 .otherwise("ok")
            )
)

catalog.write.mode("overwrite").parquet(OUTPUT_PATH)

spark.stop()
