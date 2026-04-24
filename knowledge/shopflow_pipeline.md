# Shopflow Data Platform — Guía funcional del pipeline

Shopflow es una plataforma de e-commerce ficticia usada como caso de estudio para ilustrar linaje de datos con OpenLineage y RAG.

## Arquitectura por capas

```
raw/ → staging/ → analytics/ → reports/ / ml/ / compliance/
```

| Capa | Namespace (S3) | Descripción |
|---|---|---|
| Raw | `raw/shopflow/` | Datos brutos de los sistemas operacionales. Sin transformar. |
| Staging | `staging/shopflow/` | Datos limpios, enriquecidos y normalizados. Listos para analítica. |
| Analytics | `analytics/shopflow/` | Modelo dimensional: facts y métricas agregadas. |
| Reports | `reports/shopflow/` | Informes de negocio consumibles por BI y marketing. |
| ML | `ml/shopflow/` | Predicciones de modelos de machine learning. |
| Compliance | `compliance/shopflow/` | Datos anonimizados para cumplimiento GDPR. |


## Datasets de entrada (raw)

### raw/shopflow/orders
Pedidos de clientes en bruto tal como llegan del sistema transaccional (OMS).
- **Campos clave**: `order_id`, `customer_id`, `product_id`, `quantity`, `amount`, `order_date`, `status`, `country`
- **Frecuencia de carga**: diaria, 05:00 CEST

### raw/shopflow/customers
Maestro de clientes del CRM.
- **Campos clave**: `customer_id`, `name`, `email`, `signup_date`, `segment` (premium / standard / basic), `country`, `phone`
- **Dato sensible**: `email`, `phone`, `name` son PII bajo GDPR

### raw/shopflow/products
Catálogo de productos del sistema ERP.
- **Campos clave**: `product_id`, `sku`, `name`, `category`, `price`, `brand`, `stock`


## Jobs y transformaciones

### job_shopflow_orders_clean
Limpia y particiona los pedidos raw.
- Filtra pedidos con `status = 'CANCELLED'` antes de propagar
- Extrae `year` y `month` de `order_date` para particionado en S3
- **Produce**: `staging/shopflow/orders_clean`

### job_shopflow_customers_enrich
Enriquece el maestro de clientes con métricas calculadas.
- `age_days`: días desde `signup_date` hasta hoy (`datediff`)
- `ltv_segment`: clasificación de valor de vida estimado basada en `segment` (`high` / `medium` / `low`)
- **Produce**: `staging/shopflow/customers_enriched`

### job_shopflow_products_normalize
Normaliza el catálogo de productos.
- `category_code`: versión en mayúsculas con guiones bajos para uso en sistemas downstream (`UPPER(REGEXP_REPLACE(category,' ','_'))`)
- **Produce**: `staging/shopflow/products_normalized`

### job_shopflow_sales_fact
Construye la tabla de hechos de ventas uniendo pedidos con clientes.
- Join: `orders_clean.customer_id = customers_enriched.customer_id`
- Genera `sale_id` sintético con prefijo `SF-` para trazabilidad cross-sistema
- Hereda `segment` y `ltv_segment` del cliente para análisis segmentado
- **Produce**: `analytics/shopflow/fact_sales`

### job_shopflow_product_metrics
Agrega métricas de producto por mes.
- `total_sold`: `SUM(quantity)` por `product_id`, `year`, `month`
- `total_revenue`: `SUM(amount)` por `product_id`, `year`, `month`
- `avg_price`: precio medio efectivo de venta (no precio de catálogo)
- **Produce**: `analytics/shopflow/product_metrics`

### job_shopflow_daily_revenue
Genera el informe diario de ingresos por país y segmento.
- Usado por el equipo de Revenue Operations cada mañana
- KPIs: `total_orders`, `total_revenue`, `avg_order_value`
- **Produce**: `reports/shopflow/daily_revenue`

### job_shopflow_customer_360
Vista 360º de cada cliente: historial de compras, gasto total y categoría favorita.
- `favorite_category`: categoría con más unidades compradas (moda estadística)
- Usado por los equipos de CRM y personalización
- **Produce**: `reports/shopflow/customer_360`

### job_shopflow_churn_model
Modelo de predicción de churn (abandono de cliente).
- Modelo: Gradient Boosted Trees, versión 2.1
- Features principales: `total_orders`, `last_order_date`, `total_spent` (todos de `customer_360`)
- `risk_level`: `high` (prob > 0.70) / `medium` (0.40–0.70) / `low` (< 0.40)
- **Produce**: `ml/shopflow/churn_scores`

### job_shopflow_gdpr_mask
Anonimiza los datos de clientes para cumplimiento GDPR.
- **Elimina**: `name`, `email`, `phone` (PII directa)
- **Conserva**: `customer_id` (seudónimo), `signup_date`, `segment`, `country`, `age_days`
- Dataset de salida apto para compartir con terceros y análisis de datos
- **Produce**: `compliance/shopflow/customers_anonymized`

### job_shopflow_inventory_forecast
Predicción de demanda para gestión de inventario.
- Modelo: LSTM (Long Short-Term Memory), versión 1.4
- `predicted_demand`: unidades previstas para los próximos 30 días
- `recommended_stock`: `predicted_demand * 1.15` (margen de seguridad del 15%)
- `stock_status`: `ok` / `understocked` / `overstocked` según stock actual vs recomendado
- **Produce**: `ml/shopflow/inventory_forecast`

### job_shopflow_marketing_segments
Asigna acciones de marketing a cada cliente combinando su perfil 360 y riesgo de churn.
- `recommended_action`: `retention_call` (alto riesgo) / `discount_email` (medio) / `upsell_push` (bajo)
- `campaign_code`: código de campaña para integración con plataforma de email marketing
- **Produce**: `reports/shopflow/marketing_segments`

### job_shopflow_catalog_enriched
Enriquece el catálogo de productos con predicciones de inventario.
- Combina datos maestros de producto con previsión de demanda del modelo ML
- `stock_status` advierte a los equipos de compras sobre productos con stock insuficiente
- **Produce**: `staging/shopflow/catalog_enriched`


## Flujo de linaje completo

```
raw/orders ──────────────────────────────────────────────────────────┐
                ↓ orders_clean                                        │
raw/customers → customers_enriched ──────────────────────────────────┤→ fact_sales ──→ daily_revenue
                                                                      │             ──→ customer_360 ──→ churn_scores ──→ marketing_segments
raw/products ──→ products_normalized ──→ product_metrics ─────────────┘             ──→ inventory_forecast ──→ catalog_enriched

customers_enriched ──→ customers_anonymized (GDPR, rama independiente)
```


## Preguntas funcionales frecuentes

**¿Qué datasets contienen PII?**
`raw/shopflow/customers` y `staging/shopflow/customers_enriched`. Los campos `name`, `email` y `phone` son PII directa. El dataset `compliance/shopflow/customers_anonymized` es la versión GDPR-safe.

**¿Cuál es el impacto de cambiar el schema de raw/orders?**
Afecta en cadena a: `orders_clean` → `fact_sales` → `daily_revenue`, `customer_360`, `churn_scores`, `marketing_segments`.

**¿De dónde viene el campo `ltv_segment` en fact_sales?**
Se calcula en `job_shopflow_customers_enrich` a partir de `segment` en raw/customers, y se propaga vía `customers_enriched` → `fact_sales`.

**¿Qué job genera `stock_status`?**
`job_shopflow_catalog_enriched`. Combina el stock actual de `products_normalized` con `predicted_demand` de `inventory_forecast`.

**¿Qué modelos ML existen en el pipeline?**
Dos: (1) Churn prediction GBT v2.1 en `job_shopflow_churn_model` y (2) Demand forecasting LSTM v1.4 en `job_shopflow_inventory_forecast`.
