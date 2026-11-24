# Ruta paso a paso — Finanzas Sin Filtro

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` hecho (fecha + commit).
Cada paso: **RQ** que cubre · **Construir** (acotado) · **Verificar** antes de seguir · **Reportar** (formato de CLAUDE.md + lo listado).

| # | Estado | Paso (tarea) | RQ | Construir | Verificar | Reportar además |
|---|---|---|---|---|---|---|
| 1 | [x] 2026-11-23 · 8560b30 | Base del repo en GitHub (T1.1) | RQN 01 (sin secretos) | `.gitignore`, `CLAUDE.md`, `docs/CONTEXT.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, README con enlaces; commit + push | `git status` limpio; `git ls-files` sin `markitdown/`, `.serena/`, `.env`; repo visible en GitHub | URL del commit |
| 2 | [x] 2026-11-23 · 82b8af0 | CI mínima (T1.1) | RQN 01, RQN 03 | Workflow de GitHub Actions: lint + tests de backend y `flutter analyze/test` (activado por carpeta) | Actions en verde en un push | Enlace al run |
| 3 | [x] 2026-11-23 · db3da1f | Esqueleto backend (T1.2) | — | `backend/` FastAPI con `/health`, config por `.env`, pytest | `pytest` pasa; `curl /health` → 200 | Comando de arranque |
| 4 | [~] | Esqueleto Flutter (T1.2) | RQN 02, RQN 05 | `app/` Flutter, 1 pantalla que llama `/health` | `flutter test`; corre en emulador Android (iOS si hay Mac) | Plataformas probadas |
| 5 | [ ] | Modelo de datos en Supabase (T1.3) | RQN 03, RQN 01 | Migraciones: perfil, cuentas, transacciones, categorías, presupuestos, bolsillos; montos NUMERIC; RLS | Migraciones aplican en limpio; test RLS: usuario A no lee datos de B | Lista de tablas |
| 6 | [ ] | Auth backend (T1.4) | RQF 01, RQN 01 | Supabase Auth (email + Google OAuth); FastAPI valida JWT | Tests: sin token 401, token válido 200, email no verificado bloqueado | Flujos probados |
| 7 | [ ] | Auth en app (T1.4) | RQF 01, RQN 05, RQN 02 | Login/registro mínimo + desbloqueo biométrico local | Registro → verificación → login en emulador; widget tests | Nº de campos (≤ 3) |
| 8 | [ ] | Recepción de correos (T2.1) | RQF 02, RQN 01 | OAuth al correo (solo lectura), filtro de remitentes bancarios/DIAN, tokens cifrados | Correo de prueba recibido y guardado; sin tokens en logs | Remitentes soportados |
| 9 | [ ] | Extracción vía MCP + LLM (T2.2) | RQF 02, RQN 03 | Servidor MCP de extracción; JSON validado por esquema; ambiguo → "por aclarar" | ≥ 10 correos anonimizados: precisión por campo medida; JSON inválido nunca llega a la BD | % de aciertos por campo |
| 10 | [ ] | Categorización (T2.3) | RQF 03 | Reglas por comercio primero, LLM de respaldo; categoría editable | Tests con comercios conocidos; toda transacción con categoría | Tabla de reglas |
| 11 | [ ] | Motor financiero GPS (T3.1, T3.3) | RQF 05, RQF 04, RQN 03 | Funciones puras con Decimal: saldo libre, presupuesto diario/semanal, recálculo ante gasto fuera de plan, bolsillos | Tests unitarios + bordes (fin de mes, gasto > disponible, reembolso); integración con BD | Fórmulas documentadas |
| 12 | [ ] | Pantalla "Disponible diario" (T3.2) | RQF 04, RQN 05, RQN 02 | Pantalla principal con la cifra y últimos movimientos, sin tablas/gráficos | Widget tests; prueba manual Android/iOS | Captura |
| 13 | [ ] | Coach chat (T4.1) | RQF 04, RQN 03 | Endpoint de chat: backend calcula cifras → LLM solo redacta | Test: toda cifra de la respuesta coincide con el motor | Ejemplos de respuesta |
| 14 | [ ] | Push FCM (T4.1) | RQF 02, RQN 04 | Notificación de gasto registrado + aclaración de parsing ambiguo | Correo de prueba → push recibido en dispositivo | Tiempo observado |
| 15 | [ ] | Seguridad y latencia (T4.2) | RQN 01, RQN 04 | Cifrado de campos sensibles, HTTPS, revisión de secretos; medición end-to-end | p95 correo → push < 10 s en 20 pruebas; checklist de seguridad | p50/p95 |
| 16 | [ ] | Despliegue (T4.3) | RQN 01, RQN 02 | Backend en producción (HTTPS); builds APK/IPA | Smoke test contra producción; app instalada en dispositivo | URLs/artefactos |

## Cobertura de requerimientos
- RQF 01 → 6, 7 · RQF 02 → 8, 9, 14 · RQF 03 → 10 · RQF 04 → 11, 12, 13 · RQF 05 → 11
- RQN 01 → 1, 5, 6, 8, 15, 16 · RQN 02 → 4, 7, 12, 16 · RQN 03 → 5, 9, 11, 13 · RQN 04 → 14, 15 · RQN 05 → 4, 7, 12
