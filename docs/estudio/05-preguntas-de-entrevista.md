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
no lineales, da importancias de características para explicar, y es robusto y
rápido. En validación logra exactitud ≈0,99 y ROC-AUC ≈1,0.

**¿Cómo das explicabilidad?**
Con dos cosas: las `red_flags` en texto (la explicación local: qué pasó y cuándo)
y las `feature_importances_` del modelo (la explicación global: qué pesa más). El
informe trae ambas, así que ningún veredicto es una caja negra.

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

**¿Qué cambiarías para producción?**
Cuatro cosas: (1) descentralizar el conjunto de registradores (inspectores
acreditados) en vez de un operador único; (2) una gestión seria de las claves de
los registradores; (3) una auditoría formal del contrato; y (4) un detector más
rico que cruce el historial con planes de mantenimiento del fabricante y el estado
del título, midiendo siempre contra la línea base actual. Y dejaría claro que es
una implementación de referencia, no un servicio certificado.
