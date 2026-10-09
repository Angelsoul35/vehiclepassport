# 06 — Validación con datos de coches reales

Las guías 02 y 03 explican *cómo* detecta el fraude (reglas deterministas +
RandomForest). Esta guía explica *cómo demostramos que funciona* contra
estadísticas de coches **reales**, con métricas completas (ROC-AUC, F1), el
estudio del sobre/infra-ajuste y un control que descarta la fuga de datos. El
código vive en `vehiclepassport/real_data.py` (datos e historiales) y
`vehiclepassport/real_benchmark.py` (el benchmark). Se ejecuta con:

```bash
python -m vehiclepassport.real_benchmark
```

## El problema: no hay fraude real etiquetado

Para entrenar y medir un detector hace falta saber qué historiales son fraude y
cuáles no. Pero **no existe un conjunto público de historiales de rollback reales
etiquetados**: cuando alguien vende un coche con el cuentakilómetros manipulado,
el fraude no viene con una etiqueta que diga "esto es fraude". Esa escasez de
etiquetas es, de hecho, el problema entero.

La solución es la metodología **estándar** en detección de fraude cuando las
etiquetas escasean: **población legítima real + fraude inyectado**. No es un atajo;
es la forma habitual y defendible de validar (se usa en fraude de tarjetas, de
seguros, etc.) y la declaramos con total transparencia.

## Las dos clases

Partimos de coches reales del conjunto
[`imbalet/used_cars`](https://huggingface.co/datasets/imbalet/used_cars) (432.227
anuncios reales; licencia MIT). De cada coche usamos su `year`, `mileage` (km) y
`owners` **reales**.

- **Clase legítima (real).** Con el `year`, el `mileage` y los `owners` reales de
  un coche construimos un historial plausible: el cuentakilómetros sube de ~0 al
  kilometraje real a lo largo de la edad real, a un ritmo casi constante con ruido
  de medición, y nunca baja. Como el kilometraje, la edad, los km/año y el número
  de propietarios salen de coches reales, **las distribuciones que ve el detector
  son las de vehículos reales**, no las de un generador de juguete.
- **Clase de fraude (inyectada).** Sobre un conjunto de coches reales **distinto**
  (disjunto del anterior) inyectamos:
  - un **rollback**: una lectura posterior puesta *estrictamente por debajo* de
    una anterior — exactamente el fraude del cuentakilómetros;
  - o un **salto imposible**: una gran distancia en una ventana corta — la firma
    de un cuadro de instrumentos clonado o cambiado.

La clave: las distribuciones realistas (kilometraje, edad, km/año, propietarios)
son **reales**; solo el fraude es sintético, y de forma inequívoca (una bajada en
la línea de tiempo del kilometraje *es*, por definición, fraude).

## Cómo evitamos la fuga de datos (*data leakage*)

La fuga de datos ocurre cuando información del conjunto de prueba se cuela en el
entrenamiento e infla la puntuación. La evitamos por construcción:

1. **Clases disjuntas.** Los coches legítimos y los de fraude son conjuntos sin
   intersección: ningún vehículo aparece en las dos clases, así que el modelo no
   puede "emparejar" un coche consigo mismo.
2. **Un historial por anuncio real.** Cada historial procede de un anuncio distinto;
   no se reutilizan plantillas.
3. **Separación por historiales completos.** El `train/test` y la validación
   cruzada se hacen sobre historiales enteros, de modo que un coche visto en
   entrenamiento nunca aparece en prueba.
4. **Control de barajado** (más abajo): la prueba empírica de que no hay fuga.

## Las características y sus fórmulas

El modelo no ve eventos, ve números (`features.py`). Las más importantes, con su
fórmula sobre la línea de tiempo del kilometraje (solo lecturas fiables, ver la
guía 03):

- **`total_km`** = `odómetro_último − odómetro_primero`.
- **`km_per_year`** = `total_km / age_days × 365`, donde
  `age_days = (t_último − t_primero) / 86400`. Es el ritmo anual de uso. Fíjate en
  que, aunque la edad absoluta del historial varíe, este cociente se mantiene fiel
  al km/año real del coche.
- **`n_rollbacks`** = número de pares de lecturas consecutivas con
  `odómetro_siguiente < odómetro_anterior`.
- **`max_rollback_km`** = la mayor de esas bajadas, en km.
- **`max_km_per_day`** = `máx( (odo_{i+1} − odo_i) / días_entre_i )` sobre los
  tramos crecientes. Delata los saltos imposibles.
- **`n_owners`** = número de cambios de propietario (de los datos reales).

Para la explicación por vehículo (`model_factors`) se usa un **z-score con signo**
por característica, respecto a la distribución de los coches legítimos:

```
z = (valor − media_legítima) / desviación_legítima      (recortado a ±20)
```

Positivo = "más que un coche legítimo típico".

## Las métricas, explicadas

Con la matriz de confusión (VP = verdaderos positivos, FP = falsos positivos,
FN = falsos negativos, VN = verdaderos negativos):

- **Precisión** = `VP / (VP + FP)` — de lo que marco como fraude, cuánto lo es.
- **Recall (sensibilidad)** = `VP / (VP + FN)` — del fraude que hay, cuánto cazo.
- **F1** = `2 · Precisión · Recall / (Precisión + Recall)` — la media armónica de
  las dos; castiga quedarse corto en cualquiera.
- **Exactitud (accuracy)** = `(VP + VN) / total` — fracción acertada. Útil solo
  cuando las clases están equilibradas (aquí lo están, 50/50).
- **ROC-AUC** = área bajo la curva ROC (TPR frente a FPR al mover el umbral).
  Interpretación directa: **la probabilidad de que un fraude al azar reciba una
  puntuación mayor que un coche legítimo al azar**. 0,5 es azar; 1,0 es
  separación perfecta. Mide el *ordenamiento* por riesgo, sin fijar un umbral, por
  eso es la métrica principal.

## Sobreajuste, infraajuste y la brecha

- **Infraajuste (underfitting):** el modelo puntúa bajo en *todos* lados
  (entrenamiento, CV y prueba). No ha aprendido la señal.
- **Sobreajuste (overfitting):** puntúa muy alto en entrenamiento pero cae en
  prueba. Ha memorizado, no generalizado.
- **La brecha** = `AUC_entrenamiento − AUC_prueba`. Pequeña ⇒ no sobreajusta.
- Que la **validación cruzada** (media sobre 5 pliegues) coincida con la **prueba
  reservada** indica que la cifra es estable, no un corte con suerte.

## Ejemplo trabajado: las cifras reales

Con 8.000 coches reales (de los 432.227), 4.000 historiales legítimos y 4.000 con
fraude (mediana real: 160.000 km, 14.263 km/año, 11 años, 2 propietarios), el
detector del proyecto da:

```
Validación cruzada estratificada (5 pliegues, porción de entrenamiento):
    ROC-AUC            : 0,975 +/- 0,004     # estable entre pliegues
    F1                 : 0,917 +/- 0,007

Partición reservada (probabilidad del RandomForest):
    ROC-AUC            : 0,980   (train 0,989)
    F1                 : 0,935
    exactitud          : 0,937
    brecha train-test  : 0,009               # minúscula -> no sobreajusta

Detector completo (RandomForest + reglas duras) frente a línea base:
    detector  F1 / acc : 0,939 / 0,941
    línea base F1 / acc: 0,000 / 0,500       # "siempre legítimo"
    línea base ROC-AUC : 0,500               # azar

Regla de rollback (independiente del modelo):
    recall en rollbacks explícitos: 1,000    # caza todos

Control de etiquetas barajadas:
    ROC-AUC en CV      : 0,503               # se desploma al azar

Veredicto: well-fit (bien ajustado)
```

Importancias de las características (la señal explicable):

```
max_rollback_km 0,37   n_rollbacks 0,33   max_km_per_day 0,12
km_per_year 0,07   total_km 0,04   age_days 0,02   ...
```

## Cómo leer este resultado (sin engaños)

- **No es un 1,0 fabricado.** 0,980 en prueba es alto pero claramente imperfecto;
  los saltos imposibles con magnitudes límite dejan casos genuinamente difíciles.
- **Generaliza.** La CV (0,975) coincide con la prueba reservada (0,980) y la
  brecha es 0,009: ni infraajuste (alto en ambos lados) ni sobreajuste (brecha
  minúscula).
- **Supera de largo a la línea base.** "Marcar siempre legítimo" da F1 0,000 y
  AUC 0,500; el detector da F1 0,939.
- **Las reglas garantizan lo obvio.** La regla determinista caza el **100 %** de
  los rollbacks explícitos; el RandomForest aporta los casos sutiles de
  kilometraje inconsistente.
- **El control cierra la puerta a la fuga.** Al barajar las etiquetas y
  reentrenar, el AUC cae a 0,503 (azar). Si la puntuación viniera de una fuga o de
  memorizar, *no* caería. Es la prueba decisiva de que la señal es real.

## El control de barajado, en detalle

Barajar las etiquetas rompe toda relación entre las características y la clase,
pero deja intactas las características (incluida `n_rollbacks`, que es
fortísima). Si el modelo siguiera puntuando alto, sería señal de fuga o de un
artefacto de evaluación. Que caiga a ≈0,50 demuestra que el 0,980 viene de
estructura **real** en los datos, no de un atajo.

## Para fijar la idea

- Sin fraude real etiquetado, se valida con **distribuciones reales + fraude
  inyectado**; es la metodología estándar, y se declara con transparencia.
- Sin fuga: clases disjuntas, un historial por anuncio, separación por
  historiales, y el control de barajado como prueba.
- Métrica principal **ROC-AUC** (ordena por riesgo sin umbral); **F1** combina
  precisión y recall.
- El resultado real (CV 0,975 / prueba 0,980 / brecha 0,009 / recall de rollback
  1,000 / barajado 0,503) es un detector **bien ajustado**, no un 1,0 de mentira.
