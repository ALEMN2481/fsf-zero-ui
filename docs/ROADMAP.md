# Ruta paso a paso — Finanzas Sin Filtro

Estado: `[ ]` pendiente · `[~]` en curso · `[x]` hecho (fecha + commit).
Cada paso: **RQ** que cubre · **Construir** (acotado) · **Verificar** antes de seguir · **Reportar** (formato de CLAUDE.md + lo listado).

| # | Estado | Paso (tarea) | RQ | Construir | Verificar | Reportar además |
|---|---|---|---|---|---|---|
| 1 | [x] 2026-11-23 · 8560b30 | Base del repo en GitHub (T1.1) | RQN 01 (sin secretos) | `.gitignore`, `CLAUDE.md`, `docs/CONTEXT.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md`, README con enlaces; commit + push | `git status` limpio; `git ls-files` sin `markitdown/`, `.serena/`, `.env`; repo visible en GitHub | URL del commit |
| 2 | [x] 2026-11-23 · 82b8af0 | CI mínima (T1.1) | RQN 01, RQN 03 | Workflow de GitHub Actions: lint + tests de backend y `flutter analyze/test` (activado por carpeta) | Actions en verde en un push | Enlace al run |
| 3 | [x] 2026-11-23 · db3da1f | Esqueleto backend (T1.2) | — | `backend/` FastAPI con `/health`, config por `.env`, pytest | `pytest` pasa; `curl /health` → 200 | Comando de arranque |
| 4 | [x] 2026-11-24 · f5865f5 | Esqueleto Flutter (T1.2) | RQN 02, RQN 05 | `app/` Flutter, 1 pantalla que llama `/health` | `flutter test`; corre en emulador Android (iOS si hay Mac) | Plataformas probadas |
| 5 | [x] 2026-11-24 · 8a871df | Modelo de datos en Supabase (T1.3) | RQN 03, RQN 01 | Migraciones: perfil, cuentas, transacciones, categorías, presupuestos, bolsillos; montos NUMERIC; RLS | Migraciones aplican en limpio; test RLS: usuario A no lee datos de B | Lista de tablas |
| 6 | [x] 2026-11-24 · 5519729 | Auth backend (T1.4) | RQF 01, RQN 01 | Supabase Auth (email + Google OAuth); FastAPI valida JWT | Tests: sin token 401, token válido 200, email no verificado bloqueado | Flujos probados |
| 7 | [x] 2026-11-24 · a9abae2 | Auth en app (T1.4) | RQF 01, RQN 05, RQN 02 | Login/registro mínimo + desbloqueo biométrico local | Registro → verificación → login en emulador; widget tests | Nº de campos (≤ 3) |
| 8 | [x] 2026-11-25 · c231aa5 | Recepción de correos (T2.1) | RQF 02, RQN 01 | OAuth al correo (solo lectura), filtro de remitentes bancarios/DIAN, tokens cifrados | Correo de prueba recibido y guardado; sin tokens en logs | Remitentes soportados |
| 9 | [~] 9A, 9B y LLM del 9C hechos; falta el servidor MCP | Extracción (módulo + MCP de demostración, D9) + LLM de respaldo (T2.2) | RQF 02, RQN 03 | 9A: facturas DIAN (zip/XML seguros, CUFE, comprador) y montos a Decimal · 9B: Bancolombia por reglas y escritura en `transactions` · 9C: LLM de respaldo con esquema estricto y servidor MCP mínimo; ambiguo → `pending_review` | ≥ 10 correos anonimizados: precisión por campo medida; JSON inválido nunca llega a la BD | % de aciertos por campo |
| 10 | [ ] | Categorización (T2.3) | RQF 03 | Reglas por comercio primero, LLM de respaldo; categoría editable | Tests con comercios conocidos; toda transacción con categoría | Tabla de reglas |
| 11 | [ ] | Motor financiero GPS (T3.1, T3.3) | RQF 05, RQF 04, RQN 03 | Funciones puras con Decimal: saldo libre, presupuesto diario/semanal, recálculo ante gasto fuera de plan, bolsillos | Tests unitarios + bordes (fin de mes, gasto > disponible, reembolso); integración con BD | Fórmulas documentadas |
| 12 | [ ] | Pantalla "Disponible diario" (T3.2) | RQF 04, RQN 05, RQN 02 | Pantalla principal con la cifra y últimos movimientos, sin tablas/gráficos | Widget tests; prueba manual Android/iOS | Captura |
| 13 | [ ] | Coach chat (T4.1) | RQF 04, RQN 03 | Endpoint de chat: backend calcula cifras → LLM solo redacta | Test: toda cifra de la respuesta coincide con el motor | Ejemplos de respuesta |
| 14 | [ ] | Push FCM (T4.1) | RQF 02, RQN 04 | Notificación de gasto registrado + aclaración de parsing ambiguo | Correo de prueba → push recibido en dispositivo | Tiempo observado |
| 15 | [ ] | Seguridad y latencia (T4.2) | RQN 01, RQN 04 | Cifrado de campos sensibles, HTTPS, revisión de secretos; medición end-to-end | p95 correo → push < 10 s en 20 pruebas; checklist de seguridad | p50/p95 |
| 16 | [ ] | Despliegue (T4.3) | RQN 01, RQN 02 | Backend en producción (HTTPS); builds APK/IPA | Smoke test contra producción; app instalada en dispositivo | URLs/artefactos |

## Pendientes que deben cerrarse antes del Paso 16
- "Olvidé mi contraseña" (RQF 01): enviar el correo de recuperación y abrir la app con el enlace `co.finanzassinfiltro.fsfapp://login-callback` para fijar la nueva contraseña. Quedó fuera del Paso 7 por decisión del supervisor.
- Site URL de Supabase (local y nube): si el inicio con Google falla antes de saber a qué app volver (p. ej. `OAuth state has expired` por tardar varios minutos), Supabase redirige a la Site URL; hoy esa página no existe y el usuario ve un error de conexión. Darle un destino que explique qué hacer.
- Backend en producción: desactivar `/docs` y `/openapi.json` (FastAPI los publica por defecto).
- `state` de OAuth de Gmail: guardarlo en la BD con caducidad (hoy vive en memoria; se pierde con varias instancias o al reiniciar).
- Programar `renew_watches()` a diario (los avisos de Gmail caducan a los 7 días) y probar Gmail contra la nube (suscripción push con la URL HTTPS definitiva).

## Pendientes para pasos concretos
- Antes del Paso 16: confirmar con una factura real anonimizada las rutas del XML, el código `02` de validación y la tabla de medios de pago (las 6 facturas del supervisor son simuladas y coinciden con la estructura actual; todo está en `backend/app/extract/invoice.py`), y con alertas reales los formatos de Bancolombia (las plantillas salen de alertas simuladas; lo que no encaje va a `pending_review`).
- Antes del Paso 16: serializar la extracción por usuario (dos avisos simultáneos de una alerta y su factura podrían no encontrarse y contarse dos veces) y reprocesar los correos que quedan en `pending_extraction` si la extracción falla.
- Paso 09C: servidor MCP mínimo para la demostración (D9). Pendiente de los puntos 1–9 del supervisor, que no llegaron al agente.
- Paso 16: el servidor de producción necesita Ollama con `qwen2.5:3b` (D10); medir allí la latencia en frío y en caliente.
- Paso 15: verificar la firma criptográfica XAdES del `AttachedDocument`/`ApplicationResponse` con la cadena de certificados. Hasta entonces la comprobación de la DIAN es solo estructural (riesgo: un XML falsificado con un `ApplicationResponse` inventado y el correo del comprador correcto se confirmaría; lo mitigan el DKIM del remitente y que las facturas solo se aceptan desde `INBOX`, D8).
- Paso 12: ocultar el contenido de la app en la pantalla de recientes (`FLAG_SECURE` en Android, vista de privacidad en iOS) cuando muestre datos reales.

## Cobertura de requerimientos
- RQF 01 → 6, 7 · RQF 02 → 8, 9, 14 · RQF 03 → 10 · RQF 04 → 11, 12, 13 · RQF 05 → 11
- RQN 01 → 1, 5, 6, 8, 15, 16 · RQN 02 → 4, 7, 12, 16 · RQN 03 → 5, 9, 11, 13 · RQN 04 → 14, 15 · RQN 05 → 4, 7, 12
