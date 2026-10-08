# 01 — El registro en la cadena (on-chain)

## ¿Para qué una cadena aquí?

Para tener un **historial del vehículo a prueba de manipulación**. El fraude del
cuentakilómetros ("rollback": bajar los kilómetros para que el coche parezca más
nuevo y valga más) es común y caro. Las pistas del fraude están en el historial,
pero solo si ese historial está completo y nadie lo puede reescribir después.

Un libro de mantenimiento en papel se puede falsificar. Un libro mayor en cadena,
que solo permite **añadir** (append-only) y guarda cada evento con su fecha, no se
puede editar a posteriori sin que se note. Esa es la razón de usar una cadena
aquí: integridad del registro, no "cripto".

El contrato es `contracts/src/VehicleRegistry.sol`.

## Qué guarda el contrato

Por cada vehículo (identificado por un `bytes32`), una lista de eventos que solo
crece. Cada evento tiene:

- `eventType`: el tipo (servicio, inspección, cambio de pieza, cambio de
  propietario, lectura de cuentakilómetros, incidente).
- `odometerKm`: el kilometraje en ese momento.
- `timestamp`: cuándo ocurrió.
- `dataHash`: el hash keccak del detalle completo, que vive **fuera** de la cadena.
- `recorder`: quién lo registró.

Y un contador global `totalEvents`.

## La idea clave: un registro "fiel", no "corrector"

Aquí está la decisión de diseño más importante y más fácil de equivocar.

Sería tentador que el contrato **rechazara** una lectura menor que la anterior
("eso es imposible, no lo acepto"). Sería un **error grave**. Un cuentakilómetros
que baja es **exactamente** el fraude que queremos cazar. Si el contrato lo
rechazara, el fraude ocurriría fuera de la cadena (o no se registraría), y el
historial en cadena parecería limpio mientras el coche está manipulado.

Por eso el contrato es **fiel, no corrector**: registra lo que envíe un
registrador autorizado, incluso un kilometraje que baja. El juicio sobre qué es
sospechoso vive **fuera** de la cadena, en el detector. La cadena garantiza la
**integridad** del registro (completo, ordenado, inalterado); la plausibilidad de
los valores la juzga la IA.

Así, el fraude queda **conservado como evidencia permanente** en vez de oculto.

## Quién puede escribir: registradores autorizados

Si cualquiera pudiera añadir eventos, el libro se llenaría de basura y
falsificaciones. Por eso el contrato tiene un conjunto de direcciones
**autorizadas** (`isRecorder`). Solo el operador puede cambiarlo (`setRecorder`).
En la práctica, los registradores son el servicio del pasaporte, los talleres y
los centros de inspección: quienes de verdad observan el vehículo.

Si una dirección no autorizada intenta registrar, revierte con `NotRecorder`.
También hay un error `ZeroVehicle` para el id cero. Son **errores
personalizados**, más baratos en gas y más claros que cadenas de texto.

## Privacidad: nada de VIN ni datos personales

Una cadena es permanente y pública. El VIN es un dato personal y, junto con el
historial, identifica el coche y a su dueño. Por eso:

- el vehículo es un `bytes32` (el hash keccak del VIN);
- el detalle del registro (taller, conceptos, notas) se queda fuera de la cadena;
- en la cadena solo se ancla el **hash** del detalle.

Anclar el hash permite que cualquiera verifique que un registro off-chain es el
que se guardó (porque su hash coincide), sin revelar su contenido. La
correspondencia id↔VIN vive fuera, bajo el control del operador.

## Para fijar la idea

- La cadena da un **historial append-only e inalterable**.
- El contrato es **fiel**: guarda hasta los valores sospechosos, para que el
  detector los encuentre.
- Solo **registradores autorizados** pueden escribir.
- **Sin VIN** en la cadena: solo `bytes32` y hashes de los detalles.
