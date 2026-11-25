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
- Commits pequeños, push solo tras verificación. Formato Conventional Commits
  (desde 2026-11-24; no reescribir commits ya subidos):
  - Título: `tipo(ámbito): descripción` en imperativo, en español, sin punto
    final, ≤ 72 caracteres. Tipos: feat, fix, test, docs, ci, chore, refactor, style.
    Ámbitos: app, backend, db, ci, docs.
  - Cuerpo: qué cambia y por qué, líneas ≤ 72 caracteres.
  - Pie: `Paso: NN`, `Refs: <RQ>` y `Co-Authored-By`.
  - Ejemplo:
    ```
    feat(backend): valida el JWT de Supabase en rutas protegidas

    Añade una dependencia que verifica firma, expiración y audiencia
    del token. Sin token o con token inválido responde 401.

    Paso: 06
    Refs: RQF 01, RQN 01
    Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>
    ```
- Supabase en la nube: toda acción contra el proyecto remoto (push, consultas,
  `--remote`, `--yes`, creación de usuarios) requiere confirmación explícita
  del supervisor antes de ejecutarla.
- Comandos de git que pueden perder trabajo (`reset --hard`, `rm --cached -r`, `clean`,
  `checkout -- .`, `push --force`, `rebase`) requieren confirmación explícita del
  supervisor antes de ejecutarse, aunque `git status` esté limpio. También
  `supabase db reset` (local o remoto) y cualquier borrado masivo de datos.
- Si una decisión cambia la arquitectura: registrarla en CONTEXT.md §Decisiones.

## Al cerrar cada entrega (reporte obligatorio)
Añadir entrada a CHANGELOG.md, actualizar estado en ROADMAP.md y responder con:
- Paso y RQ cubiertos · Archivos creados/modificados · Verificación (comando + resultado)
- Pendientes / riesgos · Siguiente paso
