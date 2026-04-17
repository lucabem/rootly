# OpenLineage POC — Spark + Hudi + Delta + Iceberg

Prueba de concepto que demuestra cómo OpenLineage captura el linaje de datos
cuando Spark lee tablas **Hudi** y **Delta** y escribe el resultado en tablas **Iceberg**.

```
data/hudi/orders          ──┐
                             ├──► spark SQL ──► openlineage/data/iceberg/<tabla>
data/delta/customers      ──┘
                                    ↓
                             OpenLineage events → Marquez UI
```

---

## Estructura

```
.
├── Dockerfile                  # Imagen Spark con JARs preinstalados
├── docker-compose.yml          # Marquez + Spark en red interna
├── conf/marquez.yml
├── generate_data.py            # Crea tablas Hudi y Delta con datos de ejemplo
├── inspect_lineage.py          # Muestra resumen de eventos .ndjson
├── requirements.txt
├── data/
│   ├── hudi/orders/            # Tabla Hudi fuente  (creada por generate_data.py)
│   └── delta/customers/        # Tabla Delta fuente (creada por generate_data.py)
├── openlineage/
│   ├── events.ndjson           # Eventos OpenLineage (solo en modo local)
│   └── data/iceberg/           # Warehouse Iceberg de salida
└── examples/
    ├── _spark_builder.py       # Helper compartido (transporte OL auto-detectado)
    ├── 01_hudi_to_iceberg.py   # Hudi → SQL → Iceberg (order_stats)
    ├── 02_delta_to_iceberg.py  # Delta → SQL → Iceberg (customer_profiles)
    └── 03_combined_pipeline.py # Hudi + Delta → JOIN SQL → Iceberg (sales_summary)
```

---

## Opción A — Todo en Docker (recomendado)

No requiere instalar Java ni PySpark localmente.

```bash
# 1. Construir imagen Spark y levantar todo el stack
docker compose up -d --build
# Marquez tarda ~30s en inicializar; ver estado:
docker compose logs -f marquez
```

```bash
# 2. Generar datos fuente (Hudi + Delta)
docker compose run --rm spark python generate_data.py
```

```bash
# 3. Ejecutar los pipelines
docker compose run --rm spark python examples/01_hudi_to_iceberg.py
docker compose run --rm spark python examples/02_delta_to_iceberg.py
docker compose run --rm spark python examples/03_combined_pipeline.py
```

Los scripts detectan la variable `OPENLINEAGE_URL=http://marquez:5000` (inyectada
por docker-compose) y envían los eventos directamente a Marquez via HTTP.

```bash
# 4. Ver linaje en la UI
open http://localhost:3000   # Namespace: poc-openlineage
```

---

## Opción B — Ejecución local

Requiere: **Python 3.11+** y **Java 11 o 17**.

```bash
pip install -r requirements.txt

python generate_data.py

python examples/01_hudi_to_iceberg.py
python examples/02_delta_to_iceberg.py
python examples/03_combined_pipeline.py

# Ver resumen de eventos en terminal
python inspect_lineage.py
```

En modo local los eventos se vuelcan a `openlineage/events.ndjson`.
Para enviarlos también a Marquez, levanta el stack y setea:

```bash
export OPENLINEAGE_URL=http://localhost:5000
python examples/03_combined_pipeline.py
```

---

## Cómo funciona el listener OpenLineage

El helper `examples/_spark_builder.py` detecta el entorno automáticamente:

```python
# En Docker  → OPENLINEAGE_URL está seteada → transporte HTTP a Marquez
# En local   → no está seteada              → transporte file (events.ndjson)
```

El listener `OpenLineageSparkListener` intercepta el plan de ejecución de Spark
y emite eventos con:

| Campo        | Contenido |
|--------------|-----------|
| **inputs**   | Datasets leídos: Hudi/Delta con schema y estadísticas |
| **outputs**  | Datasets escritos: tablas Iceberg |
| **jobFacets** | SQL plan lógico, versión Spark, nombre de la app |
| **runFacets** | Duración, estado (`START` / `COMPLETE` / `FAIL`) |

---

## Versiones

| Componente        | Versión  |
|-------------------|----------|
| PySpark           | 3.5.3    |
| Apache Hudi       | 0.15.0   |
| Delta Lake        | 3.2.0    |
| Apache Iceberg    | 1.6.1    |
| OpenLineage Spark | 1.43.0   |
| Marquez           | 0.47.0   |
