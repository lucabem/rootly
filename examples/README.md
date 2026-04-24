# examples/ - Shopflow Spark jobs

PySpark jobs que simulan el pipeline ETL de Shopflow y emiten eventos de linaje
con OpenLineage. Los eventos se escriben en `openlineage/events.ndjson`, que es la
fuente que consume el sistema RAG.

---

## Requisitos

- Python 3.11+ y Java 11/17 (modo local)
- PySpark (`pip install pyspark`)
- El JAR de OpenLineage se descarga automáticamente en el primer arranque via Maven

---

## Cómo funciona

El helper `_spark_builder.py` configura la `SparkSession` con:

- **JAR**: `io.openlineage:openlineage-spark_2.12:1.43.0`
- **Listener**: `io.openlineage.spark.agent.OpenLineageSparkListener`
- **Transport**: file → `openlineage/events.ndjson`
- **Namespace**: `shopflow`

Cada job llama `get_spark("nombre_del_job")` y el listener intercepta
automáticamente el plan de ejecución, emitiendo eventos START/COMPLETE con
inputs, outputs y schema.

---

## Ejecutar los jobs

```bash
cd examples/

python job_shopflow_orders_clean.py
python job_shopflow_customers_enrich.py
python job_shopflow_products_normalize.py
python job_shopflow_sales_fact.py
python job_shopflow_product_metrics.py
python job_shopflow_daily_revenue.py
python job_shopflow_gdpr_mask.py
python job_shopflow_customer_360.py
python job_shopflow_catalog_enriched.py
python job_shopflow_inventory_forecast.py
python job_shopflow_churn_model.py
python job_shopflow_marketing_segments.py
```

Los eventos se acumulan en `openlineage/events.ndjson`.

---

## Jobs y linaje

| Job | Inputs | Output |
|-----|--------|--------|
| `job_shopflow_orders_clean` | `raw/orders` | `staging/orders_clean` |
| `job_shopflow_customers_enrich` | `raw/customers` | `staging/customers_enriched` |
| `job_shopflow_products_normalize` | `raw/products` | `staging/products_normalized` |
| `job_shopflow_gdpr_mask` | `staging/customers_enriched` | `compliance/customers_anonymized` |
| `job_shopflow_sales_fact` | `staging/orders_clean` + `staging/customers_enriched` | `analytics/fact_sales` |
| `job_shopflow_product_metrics` | `staging/orders_clean` + `staging/products_normalized` | `analytics/product_metrics` |
| `job_shopflow_daily_revenue` | `analytics/fact_sales` | `reports/daily_revenue` |
| `job_shopflow_customer_360` | `analytics/fact_sales` + `analytics/product_metrics` | `reports/customer_360` |
| `job_shopflow_catalog_enriched` | `staging/products_normalized` + `ml/inventory_forecast` | `staging/catalog_enriched` |
| `job_shopflow_inventory_forecast` | `analytics/product_metrics` | `ml/inventory_forecast` |
| `job_shopflow_churn_model` | `analytics/fact_sales` + `reports/customer_360` | `ml/churn_scores` |
| `job_shopflow_marketing_segments` | `reports/customer_360` + `ml/churn_scores` | `reports/marketing_segments` |

Grafo de dependencias simplificado:

```
raw/orders ──► orders_clean ──► sales_fact ──► daily_revenue
                             │             └──► customer_360 ──► marketing_segments
raw/customers ──► customers_enriched ──► gdpr_mask           │
                             │                               └──► churn_model ──► marketing_segments
raw/products ──► products_normalized ──► product_metrics ──► catalog_enriched
                                                         └──► inventory_forecast ──► catalog_enriched
```
