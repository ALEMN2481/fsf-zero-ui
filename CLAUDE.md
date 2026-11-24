# Finanzas Sin Filtro — reglas de trabajo

Proyecto unipersonal. Idioma: español (identificadores en inglés).
Contexto: docs/CONTEXT.md · Ruta: docs/ROADMAP.md · Bitácora: docs/CHANGELOG.md

## Al empezar un turno
1. Leer en ROADMAP.md solo el paso marcado `[~]` (en curso) o el primer `[ ]`.
2. Leer CONTEXT.md solo si el paso toca un módulo nuevo.
3. Leer las 2 últimas entradas de CHANGELOG.md.

## Reglas
- Un paso a la vez. No adelantar trabajo de pasos futuros.
- Un paso termina solo cuando su "Verificación" pasa y se muestra la evidencia (salida de comando/test).
- Dinero: NUMERIC/Decimal, nunca float. Todo cálculo de saldos/presupuestos en código o BD (RQN 03).
- El LLM solo extrae JSON validado por esquema o redacta texto a partir de cifras ya calculadas; nunca calcula.
- Secretos solo en `.env` (ignorado). Nunca commitear tokens, claves ni correos reales.
- Commits pequeños: `paso-NN: <qué>`. Push solo tras verificación.
- Si una decisión cambia la arquitectura: registrarla en CONTEXT.md §Decisiones.

## Al cerrar cada entrega (reporte obligatorio)
Añadir entrada a CHANGELOG.md, actualizar estado en ROADMAP.md y responder con:
- Paso y RQ cubiertos · Archivos creados/modificados · Verificación (comando + resultado)
- Pendientes / riesgos · Siguiente paso
