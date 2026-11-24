# Bitácora de entregas (append-only, la más reciente arriba)

<!-- Plantilla
## AAAA-MM-DD · Paso NN — <título>
- RQ: …
- Cambios: archivo — qué
- Verificación: `comando` → resultado
- Commit: <hash>
- Pendientes/riesgos: …
- Siguiente: Paso NN+1
-->

## 2026-11-23 · Paso 01 — Base del repositorio
- RQ: RQN 01 (sin secretos ni herramientas locales en el repo)
- Cambios: `.gitignore`, `CLAUDE.md`, `docs/CONTEXT.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md` (nuevos); `README.md` (enlaces); `docs/` fuente (PDF + document.md)
- Verificación: `git ls-files` → 8 archivos, sin `markitdown/` ni `.serena/`; `git push origin main` → `a4e3477..8560b30`
- Commit: 8560b30 — https://github.com/ALEMN2481/fsf-zero-ui/commit/8560b30
- Pendientes/riesgos: el remoto pertenece a la cuenta ALEMN2481
- Siguiente: Paso 02 — CI mínima
