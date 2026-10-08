# Guía de estudio — VehiclePassport

Esta carpeta es una guía en español para entender VehiclePassport a fondo. El
código, los comentarios y la documentación técnica están en inglés (nivel B2) a
propósito, para que el proyecto sea creíble y sirva para practicar. Esta guía
explica el "por qué" de cada decisión en tu idioma, para estudiar con calma.

## Orden sugerido de lectura

1. **[01-registro-on-chain.md](01-registro-on-chain.md)** — el contrato
   `VehicleRegistry`, por qué es un registro solo-añadir (append-only) y "fiel",
   y por qué no guarda el VIN.
2. **[02-deteccion-de-fraude.md](02-deteccion-de-fraude.md)** — cómo se detecta el
   fraude: un modelo (RandomForest) más reglas deterministas, y por qué las
   reglas mandan.
3. **[03-caracteristicas-y-timeline.md](03-caracteristicas-y-timeline.md)** — qué
   características se extraen del historial y por qué la línea de tiempo del
   kilometraje usa solo lecturas fiables.
4. **[04-arquitectura-y-diseno.md](04-arquitectura-y-diseno.md)** — cómo encajan
   las piezas y qué decisiones de diseño se tomaron.
5. **[05-preguntas-de-entrevista.md](05-preguntas-de-entrevista.md)** — preguntas
   típicas y cómo responderlas con seguridad.

## Resumen en una frase

VehiclePassport registra el historial de un vehículo (servicios, inspecciones,
cambios de propietario, lecturas de cuentakilómetros) en un libro mayor en cadena
que nadie puede reescribir, y usa un detector de IA explicable para marcar
fraudes como la manipulación del cuentakilómetros (rollback) y los historiales
inconsistentes — sin poner el VIN ni datos personales en la cadena.
