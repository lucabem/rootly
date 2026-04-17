"""
generate_data.py
----------------
Crea las tablas fuente en formato Hudi (data/hudi/orders) y Delta (data/delta/customers)
a partir de datos sintéticos. Debe ejecutarse una vez antes de los scripts de examples/.

Uso:
    python generate_data.py
"""

import os
from datetime import datetime, timedelta

from pyspark.sql import SparkSession
from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, TimestampType
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")

HUDI_ORDERS_PATH    = os.path.join(DATA_DIR, "hudi", "orders")
DELTA_CUSTOMERS_PATH = os.path.join(DATA_DIR, "delta", "customers")

# ── Packages ──────────────────────────────────────────────────────────────────
PACKAGES = ",".join([
    "org.apache.hudi:hudi-spark3.5-bundle_2.12:0.15.0",
    "io.delta:delta-spark_2.12:3.2.0",
])


def build_spark() -> SparkSession:
    ivy_dir = os.getenv("IVY_CACHE", os.path.expanduser("~/.ivy2"))
    return (
        SparkSession.builder
        .appName("generate_data")
        .master("local[*]")
        .config("spark.jars.packages", PACKAGES)
        .config("spark.jars.ivy", ivy_dir)
        # Hudi
        .config("spark.serializer", "org.apache.spark.serializer.KryoSerializer")
        .config("spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.hudi.catalog.HoodieCatalog")
        .config("spark.sql.extensions",
                "org.apache.spark.sql.hudi.HoodieSparkSessionExtension,"
                "io.delta.sql.DeltaSparkSessionExtension")
        # Delta
        .config("spark.sql.catalog.spark_catalog",
                "org.apache.spark.sql.delta.catalog.DeltaCatalog")
        .getOrCreate()
    )


def create_orders_hudi(spark: SparkSession) -> None:
    """Escribe ~100 pedidos en formato Hudi."""
    now = datetime.now()

    rows = [
        (f"ORD-{i:04d}",
         f"CUST-{(i % 20) + 1:03d}",
         ["laptop", "phone", "tablet", "monitor", "keyboard"][i % 5],
         round(50.0 + (i * 13.7) % 950, 2),
         ["pending", "shipped", "delivered", "cancelled"][i % 4],
         now - timedelta(hours=i),   # created_at
         now - timedelta(hours=i))   # ts  (precombine field para Hudi)
        for i in range(1, 101)
    ]

    df = spark.createDataFrame(
        rows,
        ["order_id", "customer_id", "product", "amount", "status", "created_at", "ts"]
    )

    (
        df.write
        .format("hudi")
        .option("hoodie.database.name", "poc")
        .option("hoodie.table.name", "orders")
        .option("hoodie.datasource.write.recordkey.field", "order_id")
        .option("hoodie.datasource.write.precombine.field", "ts")
        .option("hoodie.datasource.write.partitionpath.field", "status")
        .option("hoodie.datasource.write.operation", "upsert")
        .option("hoodie.datasource.hive_sync.enable", "false")
        .mode("overwrite")
        .save(HUDI_ORDERS_PATH)
    )
    print(f"[OK] Hudi orders → {HUDI_ORDERS_PATH}  ({df.count()} filas)")


def create_customers_delta(spark: SparkSession) -> None:
    """Escribe 20 clientes en formato Delta."""
    countries = ["ES", "MX", "AR", "CO", "PE", "CL", "US", "BR", "FR", "DE"]

    rows = [
        (f"CUST-{i:03d}",
         f"Cliente {i}",
         f"cliente{i}@example.com",
         countries[i % len(countries)],
         f"2024-0{(i % 9) + 1}-{(i % 28) + 1:02d}")
        for i in range(1, 21)
    ]

    df = spark.createDataFrame(rows, ["customer_id", "name", "email", "country", "signup_date"])

    (
        df.write
        .format("delta")
        .mode("overwrite")
        .save(DELTA_CUSTOMERS_PATH)
    )
    print(f"[OK] Delta customers → {DELTA_CUSTOMERS_PATH}  ({df.count()} filas)")


if __name__ == "__main__":
    spark = build_spark()
    spark.sparkContext.setLogLevel("WARN")

    print("=== Generando datos de prueba ===")
    create_orders_hudi(spark)
    create_customers_delta(spark)

    print("\n=== Preview: orders (Hudi) ===")
    spark.read.format("hudi").load(HUDI_ORDERS_PATH).show(5, truncate=False)

    print("\n=== Preview: customers (Delta) ===")
    spark.read.format("delta").load(DELTA_CUSTOMERS_PATH).show(5, truncate=False)

    spark.stop()
