# 05 — Preguntas de entrevista

Preguntas típicas sobre este proyecto y cómo responderlas con seguridad.
Practica diciéndolas en voz alta en inglés también.

## Sobre la cadena

**¿Por qué usar blockchain para el historial de un coche?**
Porque el fraude del cuentakilómetros depende de reescribir el pasado, y un libro
mayor append-only hace eso imposible sin que se note. No es por "cripto": es por
la **integridad del registro**. Un libro de mantenimiento en papel se falsifica;
un registro en cadena, con fechas y solo-añadir, no.

**¿Por qué el contrato NO rechaza un kilometraje que baja?**
Porque esa bajada es justo el fraude que queremos cazar. Si el contrato la
rechazara, el fraude ocurriría fuera de la cadena y el registro parecería limpio.
El contrato es **fiel, no corrector**: guarda el valor sospechoso como evidencia
y deja el juicio al detector. La cadena garantiza integridad, no plausibilidad.

**¿Cómo proteges la privacidad si la cadena es permanente?**
No escribo el VIN ni datos personales. El vehículo es un `bytes32` (hash del VIN),
y del detalle del registro solo anclo su hash. Así se puede verificar que un
registro off-chain es el que se guardó, sin revelar su contenido. La
correspondencia id↔VIN vive fuera.

**¿Quién puede escribir y por qué?**
Solo direcciones autorizadas (`isRecorder`): el servicio, talleres y centros de
inspección. Solo el operador las gestiona (`setRecorder`). Impide basura y
falsificaciones. En producción, ese conjunto se descentralizaría (un registro de
inspectores acreditados).

## Sobre la detección

**¿Por qué combinas un modelo con reglas?**
Porque hay dos tipos de señal: hechos obvios (un rollback) y patrones sutiles
(mantenimiento irregular). Las reglas cazan lo obvio con certeza; el modelo aporta
sensibilidad a lo sutil. Y hago que **la regla dura gane**: el modelo nunca puede
dar por bueno un rollback visible. Eso es defendible ante un usuario.

**¿Por qué un RandomForest?**
Maneja características de distintas escalas sin normalizar, captura interacciones
no lineales, expone importancias de características, y es robusto y rápido. En la
evaluación sintética con semilla independiente logra F1 ≈0,979 y exactitud ≈0,983,
con CV a 5 pliegues 0,962 ± 0,011 y una brecha train-test de 0,018. Y sobre
historiales derivados de **coches reales** (`real_benchmark.py`) alcanza un
**ROC-AUC de 0,980** en test (0,975 ± 0,004 en CV), con la brecha en 0,009, la
regla de rollback con recall 1,000 y un control de etiquetas barajadas que
desploma el AUC a ≈0,50. Todas son cifras que imprimen `evaluation.py` y
`real_benchmark.py`.

**¿De dónde sacas datos de fraude real para entrenar?**
No existe un conjunto público de *historiales* de rollback reales etiquetados —el
fraude, por definición, no viene etiquetado—. Uso la metodología estándar cuando
el fraude etiquetado escasea: **población legítima real + fraude inyectado**. La
clase legítima se construye con coches reales (`imbalet/used_cars`, 432.227
anuncios): su `year`, `mileage` y `owners` reales fijan un historial plausible y
creciente, así que las distribuciones de características (km, edad, km/año,
propietarios) son reales. La clase de fraude inyecta un rollback (una lectura
posterior por debajo de una anterior) o un salto imposible en coches reales
**distintos**. Lo digo con total transparencia en el README y en la guía 06: es la
forma estándar y defendible de validar cuando no hay fraude real etiquetado.

**¿Y cómo evitas el *data leakage* en ese benchmark real?**
Por construcción: los coches de la clase legítima y los de la clase de fraude son
**disjuntos** (ningún vehículo aparece en ambas), cada historial procede de un
anuncio real distinto (no hay plantillas reutilizadas), y la separación
train/test y la validación cruzada son sobre historiales completos. La prueba
decisiva es el **control de etiquetas barajadas**: al permutar las etiquetas y
reentrenar, el AUC cae a ≈0,50; si hubiera fuga, no caería.

**¿Cómo das explicabilidad?**
Con dos cosas. Las `red_flags` en texto son la explicación **local y determinista**
(qué pasó y cuándo: "el odómetro bajó de 61.000 a 35.000 km"). Y cuando marca el
modelo sin una regla dura, `model_factors` da una explicación **específica de ese
vehículo**: no el ranking global de importancias (idéntico para todos), sino las
características de *este* historial que más se desvían de un coche legítimo, como
z-scores con signo ponderados por importancia. El modelo también expone
`feature_importances_` si se quiere la vista global. El informe trae ambas cosas,
así que ningún veredicto es una caja negra.

**¿Por qué la línea de tiempo del kilometraje ignora los cambios de propietario?**
Porque su kilometraje puede ser un valor declarado, no una medición, y la venta
es justo donde se defrauda. Construir la línea de tiempo solo con lecturas fiables
(servicios, inspecciones) evita que un valor inventado en una transferencia ancle
el análisis. Es una decisión conservadora a propósito.

## Sobre el diseño y las pruebas

**¿Por qué un `Protocol` para el registro y un fake en memoria?**
Para desacoplar el servicio de web3. La API funciona con o sin cadena, las
pruebas son rápidas, y una prueba de equivalencia comprueba que el fake y el
contrato coinciden, para que el fake no se desvíe.

**¿Qué cubren las pruebas?**
El vocabulario de eventos, la extracción de características y las banderas, el
detector (con una prueba de exactitud en datos no vistos), la API y el contrato
(en una EVM en memoria, incluyendo la autorización de registradores y la garantía
de que un rollback se conserva). Cobertura mínima en CI del 80 %.

**¿Cómo evitas el *data leakage* al evaluar el modelo?**
Separo entrenamiento y prueba con `train_test_split` estratificado y mido en el
conjunto de prueba. El modelo nunca ve en el entrenamiento los historiales con
los que se evalúa.

## Pregunta trampa

**¿Qué añadirías para un despliegue a gran escala?**
Hoy el proyecto ya valida el detector contra estadísticas reales de coches y
garantiza los rollbacks con reglas deterministas; para escalarlo añadiría cuatro
cosas: (1) descentralizar el conjunto de registradores (inspectores acreditados)
en vez de un operador único; (2) una gestión seria de las claves de los
registradores; (3) una auditoría formal del contrato; y (4) un detector aún más
rico que cruce el historial con planes de mantenimiento del fabricante y el estado
del título, midiendo siempre contra la línea base actual. Cada pieza encaja tras
la misma interfaz `assess`, así que son extensiones, no reescrituras.
