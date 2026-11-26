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
| 9 | [x] 2026-11-25 · a8103a2 | Extracción (módulo + MCP de demostración, D9) + LLM de respaldo (T2.2) | RQF 02, RQN 03 | 9A: facturas DIAN (zip/XML seguros, CUFE, comprador) y montos a Decimal · 9B: Bancolombia por reglas y escritura en `transactions` · 9C: LLM de respaldo con esquema estricto y servidor MCP mínimo; ambiguo → `pending_review` | ≥ 10 correos anonimizados: precisión por campo medida; JSON inválido nunca llega a la BD | % de aciertos por campo |
| 10 | [x] 2026-11-25 · 4800f65 | Categorización (T2.3, D11) | RQF 03 | Ingresos por dirección (salvo devoluciones); reglas propias aprendidas de las correcciones; reglas globales en `rules.toml`; si no, Otros `pendiente` y LLM local en diferido que nunca pisa al usuario; `GET /categories` y `PATCH /transactions/{id}/category`; backfill | Tests con comercios conocidos; toda transacción con categoría (conjunto del supervisor: 0 sin categoría); carrera LLM/usuario | Tabla de reglas |
| 11 | [x] 2026-11-25 · cb6fef3 | Motor financiero GPS (T3.1, T3.3, D12) | RQF 05, RQF 04, RQN 03 | Funciones puras con Decimal: saldo libre, presupuesto diario/semanal, recálculo ante gasto fuera de plan, bolsillos; `GET /gps`, `POST /budgets`, `/pockets` | Tests unitarios + bordes (fin de mes, gasto > disponible, reembolso) + propiedades (hypothesis); integración con BD | Fórmulas documentadas (CONTEXT.md §Motor financiero GPS) |
| 12 | [x] 2026-11-25 · 339e6b4 | Pantalla "Disponible diario" (T3.2) | RQF 04, RQN 05, RQN 02 | Pantalla principal con la cifra y últimos movimientos, sin tablas/gráficos | Widget tests; prueba manual Android/iOS | Captura |
| 12B | [x] 2026-11-25 · a26f071 | Ajuste visual (diseño de Figma, D14) + retoque del Paso 7 | RQF 04, RQF 01, RQN 05, RQN 02 | Tema con tokens, Inter + Unbounded empaquetadas, logo como ícono; arranque, acceso, principal con «Reservado», hoja de categoría, bolsillos con total y %, tutorial y Fuentes de Datos | Widget tests (200 %, 48×48, contraste, sin gráficos) y golden tests de 12 pantallas; prueba en emulador API 35 | Capturas frente a Figma |
| 13 | [x] 2026-11-25 · f9684e1 | Coach chat (T4.1, D15) | RQF 04, RQN 03 | `POST /coach`: tipos por reglas fijas, LLM local con marcadores (nunca cifras) y plantilla de respaldo; simulación en el motor; `coach_messages` con RLS y 90 días; chat en la app y botón ✦ | Tests con LLM simulado que intenta colar cifras; 100 % de cifras del motor; medición de 30 preguntas con Ollama real (marcador correcto, % de plantilla, latencia); emulador API 35 | Ejemplos de respuesta, capturas frente a `screen-chatbot` |
| 14 | [x] 2026-11-26 · 831e976 | Push FCM (T4.1, D16) | RQF 02, RQN 04 | Notificación de gasto registrado + aclaración de parsing ambiguo | Correo de prueba → push recibido en dispositivo | Tiempo observado |
| 15 | [ ] | Seguridad y latencia para la expo (T4.2, D17) | RQN 01, RQN 04 | Medición end-to-end en el emulador con Gmail real, separando el tramo de Google; revisión de RLS, logs sin datos personales, auditoría de dependencias, límite de uso en `/coach`, bloqueo por usuario en la extracción y reproceso de `pending_extraction` | p95 correo → push < 10 s en 20 pruebas (o limitación externa de Google documentada con datos); checklist de seguridad | p50/p95 por tramo |
| 16 | [ ] | Kit de la expo (T4.3, D17) | RQN 02, RQN 04 | Un comando que arranca todo (Docker, Supabase, backend, Ollama precargado —antes comprueba con `ollama list` que esté `qwen2.5:3b` y, si falta, lo avisa y lo descarga—, emulador, reenvíos 8000 y 54321, túnel, suscripción con `scripts.pubsub_endpoint` y audiencia, latido de FCM `expo/latido-fcm.ps1`); lista de comprobación del día (incluye regenerar los datos de la cuenta con `scripts.expo_seed --email …`); guion corto de demostración | Ensayo completo desde el PC apagado siguiendo la lista; aviso real recibido | Tiempo de arranque y del ensayo |

## Trabajo futuro: producción (D17, solo documentado)
Fuera del alcance de la expo; lo que haría falta si el proyecto continúa:
- **Despliegue con HTTPS:** backend en un servidor (contenedor), dominio y certificado; Supabase en la nube con todas las migraciones; builds firmadas APK/IPA. El servidor, **en la misma región que el proyecto de Supabase** (cada aviso hace ~13 consultas en serie, Paso 14); decidir entonces si se agrupan en una función SQL única, con la medición en la nube.
- **Ollama en el servidor** (D10) con `qwen2.5:3b`, medido en frío y en caliente.
- **Firma XAdES** del `AttachedDocument`/`ApplicationResponse` con la cadena de certificados de la DIAN (hoy la comprobación es estructural; la mitigan el DKIM y que las facturas solo se aceptan desde `INBOX`, D8).
- `/docs` y `/openapi.json` desactivados en producción.
- `state` de OAuth de Gmail en la BD con caducidad (hoy en memoria).
- `renew_watches()` programado a diario y Gmail probado contra la nube con la URL HTTPS definitiva.
- Términos y Política de privacidad (y el texto legal del acceso), logo en alta resolución (≥ 1024 px) y `FLAG_SECURE` comprobado con una build de release.

## Pendientes antes de la expo (o mejoras si se continúa)
- "Olvidé mi contraseña" (RQF 01): enviar el correo de recuperación y abrir la app con el enlace `co.finanzassinfiltro.fsfapp://login-callback` para fijar la nueva contraseña. Quedó fuera del Paso 7 por decisión del supervisor.
- Site URL de Supabase (local y nube): si el inicio con Google falla antes de saber a qué app volver (p. ej. `OAuth state has expired` por tardar varios minutos), Supabase redirige a la Site URL; hoy esa página no existe y el usuario ve un error de conexión. Darle un destino que explique qué hacer.
- Nube (trabajo futuro, D17): falta subir `20261126000000_category_question.sql` (requiere confirmación del supervisor).
- Antes de la expo: volver a conectar Gmail en los 7 días previos (el aviso de Gmail caduca a los 7 días mientras `renew_watches()` no esté programado).

## Pendientes para pasos concretos
- **Supervisor:** revisar la licencia de la plantilla de Figma «Invest App App design (Community)» y, si exige crédito, completarlo en el README (no se pudo ver: el conector de Figma no está autorizado en la sesión).
- Mejoras futuras del acceso (12B): entrar sin contraseña (enlace o código por correo) y entrar con biometría.
- ~~**Paso 12:** renovación automática del presupuesto y cifra propuesta~~ → hecho en el Paso 12 (mes calendario con el mismo monto; se propone el gasto del mes anterior con los ingresos como referencia).
- **Paso 14:** aviso con la app cerrada (FCM) ante un gasto (CU-04). Con la app abierta ya refresca por Realtime y al volver a primer plano (Paso 12).
- Limitaciones del Paso 11 (motor GPS):
  - Entre cuentas propias solo se detecta en la plantilla `transferencia_enviada` (la única que trae la cuenta de destino); lo extraído por el LLM no la trae. Los 4 dígitos no son únicos: una transferencia a la cuenta de otra persona que termine igual que una cuenta propia no contaría como gasto.
  - Una factura en efectivo nunca suma al gasto: si el efectivo no salió de un retiro registrado (p. ej. dinero recibido en mano), ese gasto no cuenta.
  - Apartar en un bolsillo se comprueba sin bloqueo: dos apartados simultáneos podrían dejar el saldo libre en negativo (se vería negativo; nada se pierde).
- Si se continúa: **medir la precisión por campo con correos reales anonimizados** (alertas de Bancolombia y facturas DIAN). La del Paso 9 se midió solo con datos simulados: el conjunto del supervisor (22) y las alertas inventadas fuera de plantilla (15).
- Si se continúa: confirmar con una factura real anonimizada las rutas del XML, el código `02` de validación y la tabla de medios de pago (las 6 facturas del supervisor son simuladas y coinciden con la estructura actual; todo está en `backend/app/extract/invoice.py`), y con alertas reales los formatos de Bancolombia (las plantillas salen de alertas simuladas; lo que no encaje va a `pending_review`).
- Paso 15: serializar la extracción por usuario (dos avisos simultáneos de una alerta y su factura podrían no encontrarse y contarse dos veces) y reprocesar los correos que quedan en `pending_extraction` si la extracción falla.
- Paso 12: `FLAG_SECURE` (solo release) y capa de privacidad hechos; falta comprobar `FLAG_SECURE` con una build de release en un dispositivo (captura negra en recientes).

## Cobertura de requerimientos
- RQF 01 → 6, 7 · RQF 02 → 8, 9, 14 · RQF 03 → 10 · RQF 04 → 11, 12, 13 · RQF 05 → 11
- RQN 01 → 1, 5, 6, 8, 15, 16 · RQN 02 → 4, 7, 12, 16 · RQN 03 → 5, 9, 11, 13 · RQN 04 → 14, 15 · RQN 05 → 4, 7, 12
