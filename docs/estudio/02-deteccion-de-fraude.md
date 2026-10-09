# 02 — La detección de fraude

## Dos tipos de señal

Para decidir si un historial parece manipulado hay dos clases de señal:

- **Señales obvias y ciertas.** Un cuentakilómetros que baja es un rollback. Un
  aumento de 120.000 km en cinco días es físicamente imposible para un coche
  particular. No son probabilidades: son **hechos** en los datos.
- **Señales sutiles y combinadas.** Un mantenimiento un poco irregular, una
  varianza de kilometraje algo alta, un número de propietarios que no cuadra con
  la edad. Ninguna por sí sola es concluyente, pero juntas levantan sospecha.

Un sistema solo de reglas se pierde las sutiles. Un sistema solo de IA podría, en
teoría, dar baja probabilidad a un historial con un rollback evidente — algo
indefendible ante un usuario ("el cuentakilómetros bajó a la vista, pero el modelo
dijo 0,3 y lo dio por bueno").

## La decisión: modelo **y** reglas, y las reglas mandan

Usamos las dos cosas, y cuando una regla dura se dispara, **gana**:

- Un **RandomForest** (bosque aleatorio), entrenado con historiales etiquetados
  (legítimos y manipulados), produce una **puntuación de riesgo** a partir de las
  características. Aporta sensibilidad a los casos sutiles.
- Unas **reglas deterministas** (`red_flags`) detectan rollbacks y saltos
  imposibles directamente, y los explican en lenguaje claro.
- Una **señal dura marca el vehículo como sospechoso pase lo que pase con el
  modelo.** El modelo puede subir la sospecha; nunca puede bajarla por debajo de
  un hecho evidente.

## ¿Por qué un RandomForest?

- Maneja bien características numéricas de escalas distintas sin normalizar.
- Captura interacciones no lineales (p. ej. "muchos km por año **y** pocos
  servicios").
- Da `feature_importances_`: qué características pesan más, una explicación global.
- Es robusto y rápido de entrenar.

### Un F1 ~0,96 — ¿legítimo o sospechoso? (over/underfitting)

Un número muy alto suele delatar sobreajuste o un test que filtra el
entrenamiento. Aquí es **legítimo**, y lo demostramos (`evaluation.py`, cifras
reales que imprime, no redondeadas al alza):

```
5-fold CV F1        : 0.962 +/- 0.011   # estable, no un split con suerte
independent test F1 : 0.979             # histories de otra semilla
independent test acc: 0.983
train-test gap      : 0.018             # minúscula -> no sobreajusta
```

Dos cosas lo hacen verificable, a diferencia de un clasificador de texto que memoriza
plantillas: cada historial de vehículo es un **sorteo aleatorio independiente**
(no una plantilla reutilizada), así que el test no filtra el entrenamiento; y las
características están **diseñadas para capturar el fraude directamente** (un
rollback **es** un delta negativo del odómetro), así que la relación aprendida es
real, no espuria. La validación cruzada (baja varianza, 0,011) y el test de
semilla independiente confirman la generalización: ni underfitting (el F1 está
alto en ambos lados) ni overfitting (brecha ≈0,018, train F1 ≈0,997 frente a test
0,979). Y las reglas duras garantizan los casos obvios pase lo que pase con el
modelo.

Esta validación usa datos sintéticos (deterministas y controlados por semilla).
Además, el detector se valida contra **estadísticas de coches reales** con
ROC-AUC, F1 y un control de etiquetas barajadas: lo explica a fondo la
**[guía 06](06-benchmark-datos-reales.md)**, con las cifras reales y las métricas
desarrolladas.

## Las reglas duras (hard flags)

Dos hallazgos marcan el vehículo como sospechoso por sí solos:

- **Rollback:** cualquier lectura menor que la anterior en la línea de tiempo del
  kilometraje. El mensaje dice los km y las fechas exactas.
- **Salto imposible:** más de `VP_MAX_KM_PER_DAY` km/día de media entre dos
  lecturas (por defecto 1500). Delata un coche clonado o un grupo de instrumentos
  cambiado.

También hay una señal blanda (un hueco muy largo sin lecturas), que aporta
contexto pero no fuerza la sospecha por sí sola.

## El informe explicable

`VehicleRiskReport` incluye:

- `risk_score`: la probabilidad del modelo.
- `is_suspicious`: la decisión final (regla dura **o** riesgo ≥ umbral).
- `red_flags`: los hallazgos en texto claro.
- `features`: las características calculadas.
- `model_factors`: la explicación **por vehículo** del modelo — no el ranking
  global de importancias (que sería idéntico para todos), sino las características
  de *este* historial que más se desvían de un coche legítimo. Se calcula como un
  z-score con signo `(valor − media_legítima) / desviación_legítima`, recortado a
  ±20 (una característica que vale 0 en todos los coches legítimos tiene varianza
  casi nula, y sin recorte daría un z astronómico sin sentido), y ponderado por la
  importancia que el modelo da a esa característica. Positivo significa "más que un
  coche legítimo típico". Así, incluso cuando marca el modelo sin una regla dura, el
  informe nombra *por qué este vehículo concreto* parece anómalo.

Así, cada veredicto se puede justificar: no es una caja negra.

## Para fijar la idea

- Señales obvias (hechos) + señales sutiles (probabilidad).
- RandomForest para lo sutil; reglas deterministas para lo obvio.
- Una regla dura **siempre** gana: el modelo no puede "votar en contra" de un
  rollback visible.
- El informe trae puntuación, decisión, banderas y factores: explicable.
