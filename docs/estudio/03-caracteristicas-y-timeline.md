# 03 — Características y la línea de tiempo del kilometraje

## De un historial a un vector de números

El modelo no entiende una lista de eventos; entiende números. `features.py`
convierte el historial de un vehículo en un **vector de características**. Estas
son las que usamos (`FEATURE_NAMES`):

- `n_events`: cuántos eventos tiene el historial.
- `age_days`: días entre la primera y la última lectura.
- `total_km`: kilómetros recorridos (última lectura menos primera).
- `km_per_year`: ritmo anual de kilometraje.
- `n_rollbacks`: cuántas veces baja el cuentakilómetros.
- `max_rollback_km`: la mayor bajada.
- `max_km_per_day`: la mayor velocidad media entre dos lecturas (delata saltos).
- `mean_interval_days`: intervalo medio entre lecturas.
- `max_gap_days`: el mayor hueco entre lecturas.
- `n_owners`: número de cambios de propietario.

Cada una aporta una pista. Por ejemplo, `max_rollback_km` alto grita fraude;
`km_per_year` muy bajo con muchos años puede indicar un rollback repartido.

## La decisión importante: qué eventos cuentan como kilometraje

No todos los eventos traen una lectura **fiable** del cuentakilómetros:

- Un **servicio**, una **inspección**, un **cambio de pieza** o una **lectura de
  cuentakilómetros** los hace alguien que miró de verdad el odómetro. El valor es
  una medición real.
- Un **cambio de propietario** o un **incidente** pueden traer un valor "último
  conocido" o declarado por una parte. Y justo en la venta es donde ocurre el
  fraude: el vendedor podría poner el número que quiera.

Por eso la **línea de tiempo del kilometraje** (y las comprobaciones de rollback,
salto y hueco) se construye **solo con los eventos de medición**
(`ODOMETER_EVENTS`). Los cambios de propietario e incidentes se registran y se
cuentan (el número de propietarios es una característica), pero su kilometraje
**no** ancla el análisis.

Es una decisión **conservadora**: un valor que un defraudador podría fijar
libremente en una transferencia no se convierte en punto de referencia de lo
"normal".

### Una consecuencia honesta

Para un coche nuevo comprado a 0 km, la transferencia de compra (odómetro 0)
queda fuera de la línea de tiempo, así que la distancia medida empieza en el
primer servicio. Es el lado seguro por el que equivocarse: el sistema nunca
confía de más en un valor de transferencia, y la primera lectura real llega poco
después.

## Las banderas rojas (red flags)

Además del vector para el modelo, `red_flags` produce hallazgos en texto, que son
la explicación local de un vehículo concreto:

- **Rollback:** "odometer rollback: 61.000 km el <fecha> bajó a 35.000 km el
  <fecha> (-26.000 km)".
- **Salto imposible:** "+120.000 km en 5 días (24.000 km/día)".
- **Hueco largo:** más de 3 años sin lecturas.

Estas banderas no dependen del modelo: se leen directamente de los datos.

## Para fijar la idea

- Las características convierten el historial en números que el modelo entiende.
- La línea de tiempo del kilometraje usa **solo lecturas fiables**, para no
  dejarse engañar por valores puestos en una venta.
- Las banderas rojas son la explicación en texto, independiente del modelo.
