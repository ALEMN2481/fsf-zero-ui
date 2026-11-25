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

## 2026-11-25 · Paso 10 — Categorización
- RQ: RQF 03, RQN 01, RQN 04 (el LLM no retrasa el aviso). Decisión **D11** (`CONTEXT.md`).
- Antes del paso: `chore: normaliza finales de línea a LF` (`e3ac33a`, `.gitattributes` con `* text=auto eol=lf`) y nueva regla en `CLAUDE.md`: los comandos de git que pueden perder trabajo requieren confirmación del supervisor (`653df80`).
- Cambios:
  - Migración `20261125030000_categorization.sql` (`e451b26`): categoría global **Ingresos**; `transactions.category_source` (`direccion`, `regla_usuario`, `regla`, `pendiente`, `llm`, `otros`, `usuario`); tabla `category_rules` (`user_id`, `merchant_key`, `category_id`; una regla por comercio) con RLS: solo reglas propias y solo hacia categorías globales o propias. pgTAP `categorization_test.sql` (9).
  - `backend/app/categorize/` (`4800f65`): `rules.toml` (reglas globales revisables) y la lógica. En línea al insertar: ingreso → Ingresos (salvo devolución, por comercio); regla propia; regla global si encaja en una sola categoría (palabra completa, sin tildes); si no, Otros `pendiente`. `run_pending` pasa los pendientes por el LLM en un hilo de fondo (`schedule`, al final de `pipeline.process`) y escribe con la condición `category_source=eq.pendiente`. LLM caído → siguen `pendiente` (se reintentan); respuesta inválida → Otros `otros`.
  - `llm.ask_category`: solo el nombre del comercio; esquema con `enum` de las categorías del usuario (sin Ingresos) y comprobación posterior; descripción breve de las categorías globales en el prompt.
  - API: `GET /categories` (globales + propias) y `PATCH /transactions/{id}/category` `{category_id}` con el JWT del usuario (RLS): 404 si el movimiento no es suyo, 422 si la categoría no es suya ni global; marca `usuario` y crea o actualiza la regla del comercio.
  - `scripts/categorize_backfill.py`: categoriza los movimientos sin categoría y los `pendiente`; si `SUPABASE_URL` no es local exige `--remote` (**no ejecutado contra la nube**: requiere confirmación). `scripts/eval_categories.py`: medición del LLM.
- Tabla de reglas globales (`rules.toml`; palabra completa, mayúsculas, sin tildes):

  | Categoría | Palabras clave |
  |---|---|
  | Alimentos | SUPERMERCADO, MINIMERCADO, EXITO, CARULLA, OLIMPICA, JUMBO, D1, ARA, ISIMO, MAKRO, PANADERIA, CAFE, CAFETERIA, RESTAURANTE, ASADERO, PIZZERIA, FRUVER, CARNICERIA, JUAN VALDEZ, TOSTAO, CREPES, EL CORRAL, FRISBY, RAPPI |
  | Transporte | UBER, DIDI, CABIFY, INDRIVE, TAXI, TRANSMILENIO, METRO DE MEDELLIN, TERPEL, PRIMAX, BIOMAX, ESSO, TEXACO, GASOLINERA, ESTACION DE SERVICIO, PEAJE, PARQUEADERO, AVIANCA, LATAM, WINGO |
  | Entretenimiento | NETFLIX, SPOTIFY, DISNEY, HBO, PRIME VIDEO, YOUTUBE, STEAM, PLAYSTATION, XBOX, CINE, CINEMA, CINEMARK, PROCINAL, TEATRO, GIMNASIO, SMARTFIT, BODYTECH |
  | Servicios | CLARO, MOVISTAR, TIGO, WOM, ETB, EPM, ENEL, CODENSA, VANTI, AFINIA, AIR-E, ACUEDUCTO, ENERGIA, GAS NATURAL, INTERNET, TELEFONIA |
  | Salud | DROGUERIA, FARMACIA, FARMATODO, CRUZ VERDE, LOCATEL, COLSANITAS, SURA, COMPENSAR, CLINICA, HOSPITAL, LABORATORIO, ODONTOLOGIA, OPTICA |
  | Otros | CAJERO (retiros y avances) |
  | Ingresos | por dirección `income`, nunca por comercio (salvo devoluciones) |

- Verificación:
  - `test_categorize.py` (45): 27 comercios conocidos → su categoría; 8 sin regla (`ARANDANOS`, `ARAÑA`, `CINEMATOGRAFIA`…); dos categorías a la vez → sin regla; cada palabra clave lleva sola a su categoría; respuestas del LLM inventadas o con campos de más → `None`; `schedule` solo lanza el hilo con LLM configurado.
  - `test_categorize_store.py` (8, Supabase local): conjunto del supervisor completo (16 alertas + 6 facturas) → **0 movimientos sin categoría**, con nómina y transferencia recibida en Ingresos, la devolución A13 en Alimentos por regla y 2 `pendiente` que el LLM (simulado) resuelve; corrección → regla del usuario usada por el siguiente movimiento del mismo comercio y no por otro usuario; 401/404/422 del endpoint; **carrera**: el usuario corrige mientras el LLM responde → gana el usuario (mutación verificada: sin la condición `pendiente` el test falla); LLM caído → sigue `pendiente`; backfill.
  - `npx supabase test db` → PASS (59); backend con Supabase local → `249 passed`; sin Supabase → `230 passed, 19 skipped`; ruff OK.
  - Medición del LLM (`python -m scripts.eval_categories`, `qwen2.5:3b`, **comercios inventados**): solo con los nombres de las categorías, 8/18 (44 %); con descripción breve de cada categoría, 15/18 (83 %) en los casos usados para ajustar el prompt y **6/12 (50 %) en casos nuevos**, escritos después; casi todos los fallos van a Otros (1 error con categoría equivocada: centro médico → Servicios). Latencia en caliente ~0,7 s, en frío ~12,6 s; no afecta al aviso.
- Pendientes/riesgos:
  - Las reglas aprendidas comparan el comercio exacto (`EXITO CALLE 80` ≠ `EXITO LAURELES`).
  - Las devoluciones anteriores al Paso 10 no guardan su plantilla: el backfill las deja en Ingresos (el usuario puede corregirlas).
  - Si una factura completa una alerta, cambia el comercio pero no se recategoriza.
  - El LLM de categorías acierta la mitad en casos nuevos y prefiere Otros; medido con datos simulados.
  - El hilo de fondo no es persistente: si el proceso se reinicia, los `pendiente` los recoge el backfill; con varias instancias hará falta una cola (Paso 16).
  - Backfill contra la nube: pendiente de confirmación del supervisor.
- Siguiente: Paso 11 (motor financiero GPS), tras la aprobación del supervisor.

## 2026-11-25 · Paso 09 (cierre) — Ventana del LLM y servidor MCP de demostración
- RQ: RQF 02, RQN 01, RQN 03 (Paso 9 completo: 9A, 9B, 9C)
- Cambios:
  - Corrección (`a699a6d`): la ventana de ±3 días del LLM se mide contra `inbound_emails.received_at` (la ingesta la recibe al insertar y la pasa a `pipeline.process`), no contra `datetime.now()`: un reproceso posterior ya no rechaza la fecha. Test: reproceso de un correo llegado hace 10 días → movimiento `pending_review`; con `now()` la misma respuesta daría `fecha` (mutación verificada: el test falla).
  - Servidor MCP (`a8103a2`, D9): `backend/app/mcp_server.py`, SDK oficial `mcp` 1.30 (la 2.x sube `starlette` a 1.x, incompatible con FastAPI 0.115), transporte stdio. Herramientas `extract_bank_alert(text, received_at?)` (plantillas y, si no encaja, LLM local; siempre `status` `confirmed`/`pending_review`/`no_movement` y `source`) y `parse_amount(text)` (`parse_cop`). Sin BD (no importa `service_db` ni `pipeline`), sin secretos (`FSF_ENV_FILE=""`: no lee `backend/.env`, y vacía las claves que lleguen por el entorno), red solo hacia un Ollama local (otra `OLLAMA_URL` desactiva el LLM). Instrucciones de MCP Inspector en el `README.md`.
- Verificación:
  - `test_mcp_server.py` (7): cliente MCP en memoria → lista exactamente las 2 herramientas; plantilla → `confirmed`; pago de tarjeta → `no_movement`; fuera de plantilla → LLM → `pending_review`; sin LLM → `pending_review` con motivo; `parse_amount` correcto y con error; proceso propio con secretos y URL externa en el entorno → sin secretos, LLM desactivado y sin módulos de BD.
  - Prueba real por stdio (cliente MCP lanzando `python -m app.mcp_server`): `parse_amount("COP 50.000")` → `50000.00`; alerta con plantilla → `confirmed` en 0,01 s; alerta fuera de plantilla → Ollama `qwen2.5:3b` → `pending_review` en 13,7 s (el modelo había salido de memoria). MCP Inspector no se ejecutó en esta sesión (descargar y ejecutar el paquete con `npx` no estaba autorizado); las instrucciones siguen su uso documentado.
  - Backend con Supabase local → `196 passed`; sin Supabase → `185 passed, 11 skipped`; `npx supabase test db` → PASS; ruff OK. Conjunto del supervisor: 22/22, 0 confirmados con monto equivocado.
- **Precisión del Paso 9 medida solo con datos simulados**: conjunto del supervisor (16 alertas + 6 facturas, 100 % por campo, 0 montos equivocados) y 15 alertas inventadas fuera de plantilla para el LLM (`qwen2.5:3b`: 92–100 % por campo, 0 montos aceptados erróneamente). **La medición con correos reales anonimizados queda pendiente antes del Paso 16** (ROADMAP).
- Pendientes/riesgos: formatos reales de alertas y facturas sin confirmar; firma XAdES (Paso 15); extracción sin bloqueo por usuario y sin reproceso automático de `pending_extraction` (antes del Paso 16); Ollama necesario en producción (D10); con el modelo fuera de memoria el LLM tarda ~12–14 s.
- Siguiente: Paso 10 (categorización), tras la aprobación del supervisor.

## 2026-11-25 · Paso 09C (parte 1) — Respaldo con LLM local (Ollama) elegido midiendo
- RQ: RQF 02, RQN 01, RQN 03, RQN 04
- Alcance: puntos 10–13 del supervisor y el plan aprobado del 9C. **Los puntos 1–9 no llegaron al agente**; el servidor MCP de demostración queda pendiente de ellos. Decisión **D10** (`CONTEXT.md`): LLM local con Ollama.
- Cambios:
  - `backend/app/extract/llm.py` — solo para alertas `sin_plantilla`. Petición a Ollama con esquema JSON (`LlmMovement`, Pydantic estricto, sin campos de más), temperatura 0 y `keep_alive` = `OLLAMA_KEEP_ALIVE` (30m). Comprobaciones contra el texto: sin otra moneda; el monto debe ser el **único** monto en COP del texto (con `$`/`COP`); últimos 4 dígitos tras `*`; comercio presente en el texto; fecha válida a ±3 días de la recepción. Si pasa, el movimiento queda **siempre** `pending_review`; si no, el correo queda en revisión sin movimiento. Ollama caído o desactivado no rompe nada.
  - `backend/app/main.py` — precarga el modelo al arrancar en un hilo aparte (`lifespan`): el arranque no espera ni falla si Ollama no está (solo un aviso con el tipo de error).
  - `backend/app/config.py` — `OLLAMA_URL`, `OLLAMA_MODEL` (`qwen2.5:3b`), `OLLAMA_KEEP_ALIVE` (`30m`), `OLLAMA_TIMEOUT` (30 s).
  - `backend/scripts/eval_llm.py` + `backend/tests/samples/llm/fuera_de_plantilla.json` — 15 alertas **inventadas** que no encajan en ninguna plantilla (12 con movimiento, 3 que deben rechazarse: dos montos, USD, sin movimiento).
  - Tests: `test_extract_llm.py` (21, Ollama simulado), integración del camino LLM en `test_extract_store.py`; `conftest.py` desactiva el LLM en todos los tests (no dependen de si Ollama está en marcha).
- Comparación (`python -m scripts.eval_llm`, `keep_alive=30m`; precisión por campo sobre las 12 con movimiento):

  | Modelo · prompt | gasto/ingreso | monto | comercio | fecha | medio | 4 díg. | aceptadas | rechazos correctos | **montos aceptados erróneamente** | caliente (mediana) | frío |
  |---|---|---|---|---|---|---|---|---|---|---|---|
  | llama3.2:3b sin ejemplos | 67 % | 75 % | 67 % | 75 % | 75 % | 75 % | 9/12 | 3/3 | **0** | 1,57 s | 11,70 s |
  | llama3.2:3b con ejemplos | 75 % | 75 % | 67 % | 75 % | 50 % | 75 % | 9/12 | 3/3 | **0** | 1,53 s | 12,97 s |
  | **qwen2.5:3b sin ejemplos** | **100 %** | **100 %** | **100 %** | **100 %** | **92 %** | **100 %** | 12/12 | 3/3 | **0** | 1,82 s | 93,17 s (1.ª vez desde disco) |
  | qwen2.5:3b con ejemplos | 100 % | 100 % | 92 % | 100 % | 92 % | 100 % | 12/12 | 3/3 | **0** | 1,67 s | 12,55 s |

  - Elegido: **qwen2.5:3b sin ejemplos** (mejores resultados; los ejemplos restan un acierto en el comercio). llama3.2:3b pierde 3 alertas porque escribe `"null"` como texto en `time` y el esquema estricto lo rechaza; aun mirando su salida cruda, acierta menos (gasto/ingreso 11/12, medio de pago 10/12).
  - Latencia de la extracción con LLM (estos números valen; la referencia de 0,14 s del supervisor era una respuesta de 10 tokens): en caliente **1,7–1,8 s** (~74 tokens con el esquema, ~50 tok/s); en frío **11,7–13 s** con el modelo en la caché del disco y **93 s** la primera vez que se lee del disco. **La carga suma ~10–11 s** cuando el modelo no está en memoria: por eso la precarga y el `keep_alive`.
  - Precarga real: con los modelos descargados, `uvicorn` responde `/health` a los 3,4 s y `qwen2.5:3b` queda en memoria a los 11,0 s (en segundo plano), con caducidad a 30 min; con `OLLAMA_URL` sin servidor, arranca igual y registra `no se pudo precargar el modelo error=ConnectError`.
- Verificación: backend con Supabase local → `188 passed`; sin Supabase → `178 passed, 10 skipped`; `npx supabase test db` → PASS; ruff OK. El conjunto del supervisor sigue 22/22 (el LLM no interviene: A04 es USD).
- Pendientes/riesgos:
  - Servidor MCP de demostración (9C, parte 2): espera los puntos 1–9.
  - El 3B confunde campos que no se pueden comprobar contra el texto (gasto/ingreso, medio de pago): todo lo del LLM queda en revisión.
  - Con el modelo fuera de memoria, la extracción con LLM no cabe en RQN 04 (< 10 s); con el `timeout` de 30 s, una primera carga desde disco (93 s) da `llm_no_disponible` y el correo queda en revisión, sin perderse.
  - Medición con una sola pasada por modelo y en esta máquina (con Docker y Supabase en marcha).
- Siguiente: puntos 1–9 del supervisor y servidor MCP mínimo.

## 2026-11-25 · Paso 09B — Alertas de Bancolombia, escritura en transactions y doble conteo
- RQ: RQF 02, RQN 01, RQN 03
- Antes del 9B: el total del XML usa el mismo rango que `parse_cop` (`MAX_AMOUNT`, cabe en `numeric(14,2)`); fuera de él → `pending_review` (`d535e97`).
- Conjunto independiente del supervisor en `backend/tests/samples/supervisor/` (16 alertas y 6 facturas simuladas + `esperado.json`), subido tal como lo entregó (`54fc1e9`). Único cambio, por decisión del supervisor (`79ec137`): A05 retiro y A14 avance → gasto (`confirmed`); A11 pago de la propia tarjeta de crédito → `no_movement` (sus compras ya se cuentan una a una).
- Cambios:
  - Migración `20261125020000_extraction.sql`: `transactions.payment_method` (lista cerrada) e `invoice_cufe` (SHA-384, único por usuario); `inbound_emails.status` admite `pending_review`. pgTAP `extraction_test.sql` (5).
  - `backend/app/extract/bancolombia.py` — 13 plantillas (compra nueva y antigua, retiro, avance, transferencia enviada y recibida, nómina, PSE, factura, QR, devolución; sin movimiento: pago de la tarjeta y compra rechazada). Comparan sin tildes ni mayúsculas, pero los datos salen del texto original. Tiene que encajar **exactamente una** vez una sola plantilla; el monto pasa por `parse_cop`, la fecha por `strptime` y el comercio debe tener 1–80 caracteres sin comas. Cualquier otra cosa → `pending_review` (sin plantilla, varias coincidencias, monto, fecha). Solo `$` (COP): USD u otra moneda no encaja.
  - `backend/app/extract/pipeline.py` — tras guardar el correo (`store.ingest`), crea o completa el movimiento con service_role. Doble conteo, en los dos órdenes de llegada: la factura completa el gasto del banco sin factura con el mismo monto exacto y fecha (en Colombia) a ±1 día (le pone el CUFE y la razón social); si la factura llega antes y se pagó con tarjeta, transferencia u otro medio, queda un movimiento `pending_review` que la alerta completa y confirma al llegar; con varios candidatos → `pending_review`; en efectivo y sin alerta → movimiento nuevo confirmado. Cuenta por los 4 últimos dígitos si hay exactamente una. Un fallo de la extracción no pierde el correo (queda `pending_extraction`, log solo con el tipo de error).
  - `backend/app/main.py` — `httpcore` en WARNING: en DEBUG registraba las cabeceras de respuesta, que repiten la URL con los filtros (el monto). Lo detectó el test de logs.
  - Tests: `test_extract_supervisor.py` (recorre todo `esperado.json`, imprime la precisión por campo y rompe la CI solo si se confirma un movimiento con monto equivocado o que no debía confirmarse), `test_extract_bancolombia.py` (13 variantes inventadas por el desarrollador que deben ir a revisión), `test_extract_store.py` (integración con Supabase local: los dos órdenes A02/F01 y los casos sin movimiento o en revisión; logs sin comercio, monto ni correo). `test_ingest_store.py`: las muestras del 08A ahora quedan `pending_review` (no siguen ninguna plantilla).
- Verificación:
  - Precisión contra el conjunto del supervisor: estado 22/22; dirección, monto, comercio, fecha, últimos 4 dígitos 13/13; medio de pago 17/17; total de factura 6/6; NIT 3/3; **confirmados con monto equivocado: 0**. F01 completa A02; F03 queda `pending_review`. Ojo: las plantillas se diseñaron a partir de estas mismas alertas, así que mide ajuste, no generalización.
  - Mutaciones detectadas: tarjeta sin alerta que crea movimiento (3 fallos), varios candidatos que toman el primero (1), sin control de varias coincidencias (1), aceptar USD (2).
  - Backend con Supabase local → `166 passed`; sin Supabase → `157 passed, 9 skipped`; `npx supabase test db` → 50 PASS; ruff check/format OK.
- Pendientes/riesgos: formatos de alertas y estructura de la factura sin confirmar contra correos reales (ROADMAP); sin bloqueo entre avisos simultáneos del mismo usuario (`shortcut:` en `pipeline.process`); un usuario podría poner a mano un `invoice_cufe` en un movimiento manual y bloquear el registro de esa factura (solo se afecta a sí mismo); la precisión de las alertas reales se medirá cuando lleguen.
- Siguiente: Paso 09C (LLM de respaldo y servidor MCP mínimo), tras la aprobación del supervisor y la elección del modelo.

## 2026-11-25 · Paso 09A — Facturas DIAN seguras y montos colombianos a Decimal
- RQ: RQF 02, RQN 01, RQN 03
- Decisión: **D9** (`CONTEXT.md`): la extracción es un módulo dentro del backend (`app/extract/`); como el documento del proyecto exige MCP, se añadirá un servidor MCP mínimo para la demostración sobre el mismo módulo (9C), fuera del camino del correo.
- Cambios:
  - `backend/app/extract/amounts.py` — `parse_cop`: `$1.234.567,89`, `COP 50.000`, `$50,000.00`, `1,5`… → `Decimal` con 2 decimales; rechaza cero, negativos, grupos de miles mal formados, mezclas ambiguas y > `numeric(14,2)`. Sin `float`.
  - `backend/app/extract/invoice.py` — `.zip` en memoria con límites (≤ 10 archivos, ≤ 5 MB descomprimidos leídos con tope, compresión ≤ 100:1, sin rutas `..`/absolutas, sin `.zip` anidado ni cifrado, exactamente un XML); XML con `defusedxml` (`forbid_dtd`, sin entidades), también en la factura y la respuesta embebidas en CDATA. Lee número, CUFE, fecha/hora (−05:00 si no trae zona), emisor y NIT, correos del comprador, total y moneda, medio de pago. `check_invoice` → `confirmed` solo si `ResponseCode` = `02`, el CUFE de la factura es el del `ApplicationResponse` (y tiene formato SHA-384), el correo del comprador es el Gmail conectado (en Gmail sin puntos ni `+etiqueta`) y la moneda es COP; si no, `pending_review` con un motivo sin datos personales.
  - Todas las rutas del XML, el código `02` y la tabla de medios de pago están juntas al principio de `invoice.py` para ajustarlas con una factura real anonimizada (la de la prueba del 08B la creó el agente y no sirve para confirmar la estructura).
  - `backend/tests/samples/dian/attached_document.xml` — muestra **inventada** con la estructura del Anexo Técnico (UBL 2.1).
  - `backend/requirements.txt` — `defusedxml==0.7.*`.
- Verificación:
  - `pytest tests/test_extract_amounts.py tests/test_extract_invoice.py` → `63 passed` (25 de montos; 38 de facturas: lectura, comprador, DIAN, XML inseguro con XXE y "billion laughs" también dentro del CDATA, 9 casos de `.zip` peligroso, `.zip` cifrado).
  - Mutaciones: quitar la comprobación de la DIAN, la del comprador o el límite de compresión hace fallar los tests (2, 2 y 1 fallos).
  - Suite completa con Supabase local → `141 passed`; sin Supabase → `135 passed, 6 skipped`; ruff check/format OK.
- Pendientes/riesgos:
  - La estructura del XML está tomada del Anexo Técnico y sin confirmar contra una factura real; el significado del código `02` y la tabla de medios de pago no se pudieron confirmar en una fuente oficial en línea.
  - Firma XAdES sin verificar hasta el Paso 15: la comprobación de la DIAN es solo estructural.
  - El módulo aún no está conectado al flujo del correo ni escribe en `transactions` (9B).
- Siguiente: Paso 09B (Bancolombia por reglas, escritura en `transactions` y doble conteo con facturas), tras la aprobación del supervisor.

## 2026-11-25 · Paso 08 (seguimiento) — Test intermitente con Supabase local y cierre de la prueba de Gmail
- RQ: RQN 01
- Causa del error intermitente (`77 passed, 1 error`, 53 s, máquina cargada con emulador y Gradle): falló la preparación del fixture `users`. Huella: quedaron en el Supabase local `fsf-a` y `fsf-b` creados durante esa ejecución; `a` inició sesión y `b` se creó, así que lo que falló fue el `sign_in` de `b` (el `.json()["access_token"]` no tenía comprobación). Sin `finally`, los dos usuarios quedaron huérfanos. No se conserva la traza (la salida se recortó con `tail -1`); lo más probable es el timeout de 10 s de GoTrue con bcrypt bajo carga. Descartado el límite de `sign_in_sign_ups` (30/5 min): 4 ejecuciones seguidas (44 llamadas en ~80 s) pasan.
- Cambios: `backend/tests/conftest.py` — limpieza en `finally` aunque la preparación falle a medias y `assert` del `sign_in` con código y cuerpo; `backend/tests/local_supabase.py` — timeout de 30 s.
- Verificación: test temporal que hace fallar el `sign_in` de `b` → `ERROR … sign_in 504: simulado` y 0 usuarios huérfanos después; suite completa con Supabase local → `78 passed`, 0 huérfanos; sin Supabase → `72 passed, 6 skipped`; `npx supabase test db` → 45 PASS; ruff check/format OK. Se borraron los 2 huérfanos.
- Gmail de prueba: suscripción `gmail-fsf-push` borrada por el supervisor; permiso revocado con `gmail.disconnect` (revoke → HTTP 200; el refresh token devuelve `invalid_grant` después) y fila borrada (0 conexiones).
- CI de `9149381`: CI https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45550245555 · DB https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45550245496
- Siguiente: plan del Paso 09.

## 2026-11-25 · Paso 08B — Conexión con Gmail, avisos de Pub/Sub y prueba de punta a punta
- RQ: RQF 02, RQN 01, RQN 04
- Hecho por el supervisor (no verificado por el agente): Gmail API y Pub/Sub activadas, `gmail.readonly` en el consentimiento ("En pruebas"), `http://localhost:8000/gmail/callback` en el cliente web, tema `gmail-fsf` con `gmail-api-push@system.gserviceaccount.com` como publicador, cuenta de servicio para el push; variables en `backend/.env` (no leído).
- Parte local (hecha):
  - Migración `gmail_connections` (una por usuario; `refresh_token` cifrado con AAD `user_id`; `history_id`; `watch_expires_at`; `status` `active`/`needs_reconnect`). RLS: el usuario solo ve estado, dirección y fechas; nunca el token ni el `history_id`.
  - `backend/app/gmail.py`: URL de consentimiento con solo `gmail.readonly`, `include_granted_scopes`, `access_type=offline`, `prompt=consent` y PKCE; intercambio del código en el backend; `users.watch`; verificación del token OIDC de Pub/Sub (firma de Google, audiencia, emisor, cuenta de servicio y `email_verified`); lectura por `history.list` → prefiltro por De/Asunto con `format=metadata` → solo los candidatos se descargan con `format=raw`; duplicados por el **id de mensaje de Gmail** (`gmail:<id>`); `invalid_grant` → `needs_reconnect` sin reintentos; `renew_watches()` (diaria, a programar en el Paso 16); `disconnect` revoca y borra.
  - `backend/app/main.py`: `POST /gmail/connect`, `GET /gmail/callback` (vuelve a `co.finanzassinfiltro.fsfapp://gmail-connected?status=ok|error`), `POST /gmail/push`, `POST /gmail/disconnect`; `/me` añade `gmail_status`. El log de accesos de uvicorn oculta la query (lleva el código de Google) y `httpx` solo registra avisos (sus URLs pueden llevar la dirección de Gmail en los filtros).
  - App: botón "Conectar Gmail" / "Reconectar Gmail", estado "Gmail conectado" o "La conexión con Gmail se cayó", refresco al volver a la app; enlace `gmail-connected` en Android.
- **Limitación para producción:** el `state` de OAuth (con el verificador PKCE) se guarda en memoria del backend; con varias instancias o tras un reinicio se pierde y la conexión falla. Antes del Paso 16, guardarlo en la BD con caducidad.
- **Requisito para el Paso 09:** una factura solo se registra si el XML está dirigido al usuario (comprador) y, si es posible, si la firma de la DIAN del `AttachedDocument` es válida; si no, queda `pending_review`. DKIM prueba el dominio del remitente, no la legitimidad de la factura.
- **Requisito para el Paso 09:** abrir los `.zip` y XML de forma segura: límite de tamaño descomprimido y de número de archivos, y XML sin entidades externas (p. ej. `defusedxml`).
- Ajustes durante la prueba (decididos por el supervisor):
  - **D8** (`CONTEXT.md`): todo el buzón; bancos desde `INBOX` y `SPAM`, facturas solo desde `INBOX`; siempre fuera Enviados, Borradores y Papelera (y archivados). Tests: banco en Spam se guarda, factura en Spam se descarta, Enviados/Borradores/Papelera/archivado se descartan, `watch` e `history` sin filtro de carpeta.
  - App: con `status=error` en la vuelta muestra "No se pudo conectar Gmail, inténtalo de nuevo" y refresca el estado.
  - Logs de diagnóstico sin secretos: en `/gmail/callback` solo tipo de error, paso (`token`/`profile`/`watch`), código HTTP y motivo de Google (nunca `log.exception`: la traza o el mensaje podrían llevar el código o un token); en `/gmail/push`, la categoría del rechazo (p. ej. `InvalidAudienceError`). Latencia Gmail → guardado en el log (RQN 04). Los logs de la app salen por consola.
- Prueba de punta a punta (túnel rápido de Cloudflare autorizado solo para la prueba; llamadas a Gmail solo con la cuenta del supervisor; su URL no se guarda en el repo):
  - Fallo 1: `paso=profile http=403 motivo=PERMISSION_DENIED/accessNotConfigured` → **la Gmail API no estaba activada** en el proyecto del cliente (la activó el supervisor).
  - Fallo 2: no llegaban avisos → la suscripción `gmail-fsf-push` **no existía**; se creó (los avisos publicados antes no se entregan).
  - Fallo 3: avisos rechazados con `InvalidAudienceError` → `PUBSUB_PUSH_AUDIENCE` en `backend/.env` no coincidía con la audiencia de la suscripción (una `s` de más al final); corregido.
  - 1.er correo (factura de prueba): llegó a **Spam** → descartado sin descargarlo por D8 (comprobación real de "factura en Spam se descarta").
  - 2.º correo: reenvío con asunto `RV: …` → el prefiltro lo descartó (el asunto DIAN debe empezar por el NIT). Del aviso al procesado: ~7 s.
  - 3.er correo (nuevo, en Recibidos): **guardado** en `inbound_emails` con `rule=factura_electronica`, `status=pending_extraction`, `key_version=1`, 13 312 bytes cifrados sin el texto en claro; se descifra con su clave y AAD y solo conserva el `.zip`; `message_hash = sha256('gmail:' + id de Gmail)`.
  - **Latencia observada (Gmail recibe → guardado): 10 024 ms** (una medición, con túnel y backend local). Está en el límite de RQN 04 (< 10 s); la medición formal es del Paso 15.
  - Log del backend de toda la prueba: 0 apariciones de direcciones de Gmail, `ya29.`, `1//`, `code=`, `state=`, `refresh_token`, `access_token` y del asunto de prueba.
  - Al terminar: túnel cerrado (sin procesos `cloudflared`; la URL ya no responde); la suscripción la borra o desactiva el supervisor en la consola.
- Verificación automática: backend 72 passed sin Supabase (6 saltados) y **78 passed** con Supabase local en dos ejecuciones seguidas (una primera ejecución dio 1 error que no se repitió; causa no confirmada, posible lentitud del stack local); pgTAP 45 (el test de retención ahora mira solo sus usuarios: fallaba con el correo real guardado en local); app 21 passed, `flutter analyze` sin problemas.
- Commits: d3a19f4 (conexión y webhook), 1dbf809 (D8 y diagnósticos), c231aa5 (aviso de error en la app)
- Pendientes (en `ROADMAP.md`): antes del Paso 16, desactivar `/docs` y `/openapi.json` en producción, `state` de OAuth en la BD, programar `renew_watches()` y probar Gmail contra la nube; Paso 09, `.zip`/XML seguros y legitimidad de la factura.
- Riesgos:
  - Latencia en el límite (10,0 s en la única medición): el aviso de Pub/Sub tardó ~7 s; revisar en el Paso 15 (p. ej. procesar el aviso en segundo plano y responder antes).
  - Un correo que pasa de Spam a Recibidos **después** de llegar no se procesa (Gmail lo registra como cambio de etiqueta, no como mensaje nuevo). Afecta poco a los bancos (se aceptan desde Spam).
  - Las facturas reenviadas (`RV:`/`Fwd:`) no se aceptan, a propósito.
  - En modo "En pruebas" el `refresh_token` caduca a los 7 días → `needs_reconnect`; el aviso al usuario es del Paso 14.
  - Los logs de acceso de uvicorn guardan la IP de quien llama (Google y el propio túnel); no son secretos, pero son datos personales si el backend se usa en producción.
- Siguiente: Paso 09 — Extracción vía MCP + LLM (no iniciado)

## 2026-11-25 · Paso 08A — Recepción local: filtro, DKIM, cifrado y guardado
- RQ: RQF 02, RQN 01
- Decisión del supervisor: opción A (Gmail `gmail.readonly` + Pub/Sub), con B (reenvío) como plan de salida → D7 en `CONTEXT.md`. El paso se divide en 8A (local, sin nube) y 8B (Gmail, Pub/Sub, túnel, prueba de punta a punta).
- Cambios:
  - `supabase/migrations/20261125000000_inbound_emails.sql`: tabla `inbound_emails` (metadatos, `message_hash` único por usuario, `status`, `key_version` + `raw_encrypted`); RLS: el usuario solo lee **metadatos** propios (permisos por columna; el contenido y la versión de clave quedan fuera), no escribe; función `purge_inbound_emails()` (vacía el contenido 30 días tras extraer o 90 tras recibir; solo backend).
  - `backend/app/ingest/mail.py`: reglas (Bancolombia `alertasynotificaciones@…` se guarda; `validaciondeseguridad@…` se descarta; factura electrónica por asunto DIAN con tipo `01` + `.zip`/`.xml`); DKIM solo del `Authentication-Results` de `mx.google.com` de más arriba, con `header.d` (o el dominio de `header.i`, que es lo que suele poner Gmail) igual al de la regla; en facturas, alineado con el dominio del remitente; limpieza de adjuntos (bancos: ninguno; facturas: solo `.zip`/`.xml`); tope de 5 MB guardado y 30 MB leído.
  - `backend/app/ingest/crypto.py`: AES-256-GCM con versión de clave (`EMAIL_KEYS="1:…,2:…"`, cifra con la más alta) y AAD `usuario:hash` (el texto cifrado no sirve en otra fila).
  - `backend/app/ingest/store.py`: `ingest(user_id, raw, source)` → `stored` / `duplicate` / `no_rule` / `discarded` / `dkim` / `too_large`; inserta con `service_role` (D4) e ignora duplicados; logs solo con id, regla y dominio.
  - `backend/app/config.py`, `.env.example`, `requirements.txt` (`cryptography` explícito; ya venía con `pyjwt[crypto]`).
  - Tests: `test_ingest_mail.py` (18, sin red), `test_ingest_store.py` (2, Supabase local), `supabase/tests/inbound_emails_test.sql` (12 pgTAP). Muestras inventadas en `backend/tests/samples/` (dominios `.example`, NIT ficticio, texto "EJEMPLO"; ningún correo real). Ayudantes de Supabase local movidos a `tests/local_supabase.py` + `conftest.py`.
  - `supabase/tests/rls_test.sql`: el conteo de perfiles solo mira los dos usuarios del test (fallaba en local con usuarios previos; en la CI pasaba por tener la BD limpia).
- Verificación:
  - `npx supabase migration up` → aplicada en local · `npx supabase test db` → 39 tests, PASS.
  - Con Supabase local: `REQUIRE_SUPABASE=1 pytest backend` → 38 passed. Sin Supabase: 33 passed, 5 skipped.
  - Casos cubiertos: cabecera falsa inyectada debajo de la de Gmail → rechazado; `dkim=pass` de otro dominio → rechazado; `Authentication-Results` de otro servidor → no se confía; duplicado → no se guarda dos veces; el contenido en la BD no contiene el texto del correo y se descifra con su clave y AAD; rotación de clave; el usuario no puede leer `raw_encrypted` (401/403) y B no ve los correos de A; los logs (nivel DEBUG, todos los loggers) no contienen cuerpo, asunto, direcciones, `service_role`, clave de cifrado ni token.
  - `ruff check backend` y `ruff format --check backend` → OK.
  - CI (7f7810a) → CI success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45531774957 · DB success (migración + 39 pgTAP + pruebas de integración) https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45531774955
- Commits: 6cb38d0 (migración y pgTAP), 7f7810a (ingesta y tests)
- Pendientes (8B): conexión con Gmail (OAuth propio, `gmail_connections` con token cifrado, `needs_reconnect` ante `invalid_grant` visible en `/me`), webhook de Pub/Sub con OIDC, renovación diaria de `watch`, túnel y prueba de punta a punta. Confirmar con cabeceras reales: remitentes de otros bancos, formato DKIM de Gmail (`header.i`/`header.d`) y el código `01` del asunto DIAN.
- Riesgos: el formato del asunto DIAN se tomó de una copia antigua de la norma; si las facturas reales difieren, se ajusta la regla. En la migración se perdió un intento con la CLI (`migration new` se colgó y dejó un archivo vacío que se borró y se marcó `reverted` en el historial local).
- Siguiente: Paso 08B — tras recibir las instrucciones de Google Cloud y la confirmación del supervisor

## 2026-11-24 · Paso 07 (Parte B y cierre) — Google OAuth y ajustes
- RQ: RQF 01, RQN 01, RQN 02, RQN 05
- Hecho a mano por el supervisor (sin verificar por el agente, salvo lo que se prueba en local): cliente OAuth "Aplicación web" en Google Cloud; Google activado en el Supabase de la nube; `co.finanzassinfiltro.fsfapp://login-callback` en Redirect URLs de la nube; `supabase/.env` con las credenciales (no leído por el agente).
- Cambios:
  - `app/lib/auth_screen.dart`: botón "Continuar con Google" → `getOAuthSignInUrl(google, redirectTo: enlace de la app)` (PKCE) y lo abre en el navegador externo; el formulario sigue con 2 campos.
  - `supabase/config.toml`: `[auth.external.google]` con `env(SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID/SECRET)`. `.github/workflows/db.yml`: valores ficticios para que `supabase start` arranque en la CI.
  - Nombre de la app: "Finanzas Sin Filtro" (`android:label` y `CFBundleDisplayName`).
  - Diálogo de desbloqueo en español con `AndroidAuthMessages` e `IOSAuthMessages` (`local_auth_android`, `local_auth_darwin` y `url_launcher` pasan a dependencias directas; mismas versiones que ya venían).
  - `app/lib/home_screen.dart`: `/me` espera hasta 10 s (`meTimeout`).
  - Tests: Google abre `/auth/v1/authorize` con `provider=google` y `redirect_to` de la app; el diálogo recibe los textos en español; `/me` responde a los 7 s → verificada; sin respuesta a los 10 s → no verificada.
- Verificación:
  - `flutter analyze` → No issues found · `flutter test` → 15 passed.
  - Supabase local reiniciado: `/auth/v1/settings` → `google: true`; `/authorize?provider=google` → 302 a `accounts.google.com` con `redirect_uri=http://127.0.0.1:54321/auth/v1/callback` y el `client_id` resuelto desde `supabase/.env`.
  - Emulador: diálogo de desbloqueo con título "Finanzas Sin Filtro", "Usa tu huella o el bloqueo de pantalla" y "Desbloquea la app para ver tu información"; los botones "Cancel"/"Use PIN" los pone Android según el idioma del sistema (emulador en inglés).
  - Google de punta a punta (el supervisor escribió su cuenta en el emulador): primer intento → `400: OAuth state has expired` (pasaron ~11 min entre abrir la página y volver) y Chrome acabó en la Site URL `127.0.0.1:3000`, que no existe. Segundo intento → `/callback` 302 → `/token` 200 (`pkce`) → la app muestra "Backend conectado" y "Sesión verificada"; backend `/me` 200; en la BD local hay un usuario con identidad `google` y correo confirmado.
  - CI (a9abae2) → CI success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45528604670 · DB success (con los valores ficticios de Google) https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45528604820
- Commits: a9abae2
- Pendientes:
  - Antes del Paso 16 (en `ROADMAP.md`): "Olvidé mi contraseña"; dar destino a la Site URL para errores de OAuth.
  - Paso 12 (en `ROADMAP.md`): ocultar la app en la pantalla de recientes (`FLAG_SECURE`) cuando muestre datos reales.
  - Paso 16: Google y registro contra la nube (no se probó; solo local).
- Riesgos: si el usuario tarda varios minutos en Google, el estado de OAuth caduca y no vuelve a la app (ver pendiente de la Site URL). Paso 08: `gmail.readonly` es un permiso restringido (anotado en la Parte A).
- Siguiente: Paso 08 — Recepción de correos (no iniciado; el supervisor revisará antes su plan)

## 2026-11-24 · Paso 07 (Parte A) — Acceso con correo, sesión cifrada y bloqueo local
- RQ: RQF 01, RQN 01, RQN 02, RQN 05
- Antes de empezar:
  - Seguimiento del Paso 06 (ddd1b9e) → CI success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45513697610 · DB success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45513697682
  - `style(backend)` (b4d4c97): `ruff format` en el backend; la CI fija ruff 0.17.6 y corre `ruff format --check`; se añade el tipo `style` a las reglas de `CLAUDE.md` → CI success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45514859502 · DB success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45514859525
- Decisiones del supervisor: sesión cifrada; bloqueo al abrir y tras ≥ 5 min en segundo plano (acepta PIN; sin biometría ni PIN no bloquea y avisa una vez); prueba manual en local; Google en local (Parte B). Registradas como D6 en `CONTEXT.md`.
- Cambios:
  - `app/pubspec.yaml`: `supabase_flutter` 2.18, `flutter_secure_storage` 11.2, `local_auth` 3.0.
  - `app/lib/session_storage.dart` (nuevo): `LocalStorage` de Supabase sobre almacenamiento seguro.
  - `app/lib/auth_screen.dart` (nuevo): un formulario de **2 campos** (correo, contraseña) para registro e inicio de sesión; validación local (correo válido, ≥ 8 caracteres); `emailRedirectTo = co.finanzassinfiltro.fsfapp://login-callback`; mensajes en español por código de error.
  - `app/lib/main.dart`: inicializa Supabase con la sesión cifrada; bloqueo con `local_auth` al abrir y tras ≥ 5 min en segundo plano; aviso único "Activa un bloqueo de pantalla para proteger tu información"; cerrar sesión borra la sesión del almacenamiento seguro aunque falle la red.
  - `app/lib/home_screen.dart` (nuevo): `/health` y `/me` con el token (prueba de punta a punta con el backend del Paso 06).
  - Android: `intent-filter` del enlace, `USE_BIOMETRIC`, `FlutterFragmentActivity`, tema AppCompat; `kotlin.incremental=false` (atajo: falla con el proyecto en D: y la caché de pub en C:). iOS: `CFBundleURLTypes` y `NSFaceIDUsageDescription` (sin probar, no hay Mac).
  - `supabase/config.toml`: el enlace de la app en `additional_redirect_urls`. `app/env.example.json`: plantilla de `--dart-define-from-file=.env.json` (`.env.json` queda ignorado).
  - Tests: `app/test/auth_test.dart` (9 tests) y `health_test.dart` adaptado.
- Verificación:
  - `flutter analyze` → No issues found · `flutter test` → 12 passed (2 campos; validación sin llamadas; registro con `redirect_to` correcto; correo sin confirmar; login sin pedir biometría; bloqueo al abrir y fallo que mantiene el bloqueo; 4:59 no bloquea y 5:00 sí; sin bloqueo de pantalla avisa una sola vez; cerrar sesión borra la clave del almacenamiento seguro).
  - Emulador Android (Pixel_8, API 37) contra Supabase y backend locales (`adb reverse` de 54321, 54324 y 8000):
    - Registro en la app → "Revisa tu correo para confirmar la cuenta" → correo en Mailpit con `redirect_to=co.finanzassinfiltro.fsfapp://login-callback` → al abrir el enlace, Android abre la app, `/token` 200 (PKCE) y la app entra con "Backend conectado" y `/me` 200 ("Sesión verificada" tras reabrir; ver riesgos).
    - Sin PIN en el dispositivo: abre sin bloqueo. Con PIN: al abrir pide el PIN del sistema ("Desbloquea Finanzas Sin Filtro"); cancelar deja la app bloqueada; con el PIN entra.
    - Segundo plano real: 60 s → no bloquea; 308 s → pide desbloqueo.
    - Huella registrada en el emulador (`adb emu finger touch 1`): al abrir pide huella y con ella entra.
    - Cerrar sesión → formulario; al reabrir la app no hay sesión. Inicio de sesión con contraseña → entra sin pedir biometría y `/me` 200.
  - Nº de campos del formulario: **2** (≤ 3).
  - CI (80878a9) → CI success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45522853744 · DB success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45522853671
- Commits: 531f5ab (configuración), 80878a9 (acceso y bloqueo)
- Pendientes:
  - Parte B del Paso 07: Google OAuth (necesita el cliente OAuth de Google y `supabase/.env` creados por el supervisor).
  - Antes del Paso 16: "Olvidé mi contraseña" (anotado en `ROADMAP.md`).
  - Nube: añadir `co.finanzassinfiltro.fsfapp://login-callback` en Authentication → URL Configuration → Redirect URLs (lo hace el supervisor; sin eso el correo de confirmación de la nube no vuelve a la app).
  - Textos del sistema en inglés: el título del diálogo de biometría ("Authentication required") y el nombre de la app en Android ("fsf_app").
- Riesgos:
  - **Paso 08:** `gmail.readonly` es un permiso restringido de Google. Funciona en modo "En pruebas" con hasta 100 usuarios de prueba, pero publicar la app exige la verificación de seguridad de Google.
  - El primer `/me` tras reiniciar el emulador superó el tiempo de espera de 5 s de la app (el backend respondió 200, pero tarde); en llamadas siguientes tardó 0,3–0,5 s. Si se repite fuera del emulador, conviene subir ese tiempo para `/me`.
  - La pantalla con el diálogo de PIN sale negra en las capturas (Android protege esa ventana); la evidencia de esos pasos es el volcado de la interfaz (`uiautomator`).
- Siguiente: Paso 07 (Parte B) — Google OAuth

## 2026-11-24 · Paso 06 (seguimiento) — Recarga del JWKS limitada y con caducidad
- RQ: RQN 01
- Cambios:
  - `backend/app/auth.py`: las claves en memoria caducan a los 10 min (`JWKS_TTL = 600`); la recarga por `kid` desconocido ocurre como mucho una vez cada 60 s (`KID_REFETCH_INTERVAL`); dentro de ese intervalo responde 401 sin descargar.
  - `backend/app/config.py`: lee `backend/.env` con ruta absoluta relativa al archivo (funciona arrancando desde la raíz).
  - `backend/tests/test_auth.py`: reloj falso; +2 tests (20 `kid` inventados → una sola recarga y otra tras 61 s; caducidad a los 10 min → nueva descarga).
- Verificación:
  - `ruff check backend` → All checks passed
  - `pytest backend -q` (sin Supabase local) → 15 passed, 3 skipped
  - Desde la raíz, con un `backend/.env` temporal `APP_ENV=prueba-ruta` → `settings.app_env == "prueba-ruta"` (archivo borrado después)
- Riesgo resuelto: una clave revocada deja de aceptarse en ≤ 10 min sin reiniciar el backend.
- Siguiente: plan del Paso 07 (pendiente de aprobación)

## 2026-11-24 · Paso 06 — Auth backend
- RQ: RQF 01 (registro, login y verificación), RQN 01 (JWT validado, RLS desde el backend)
- Reglas: Conventional Commits y confirmación obligatoria para acciones en la nube, en `CLAUDE.md` (e3282bc).
- Cambios:
  - `supabase/config.toml`: `minimum_password_length = 8`, `[auth.email] enable_confirmations = true` (entorno local y CI).
  - `backend/app/auth.py` (nuevo): dependencia `current_user`. Valida la firma con el JWKS, `exp`, `aud=authenticated` e `iss=<SUPABASE_URL>/auth/v1`. Solo acepta ES256/RS256 (rechaza `none` y HS256). Con un `kid` desconocido recarga el JWKS una sola vez.
  - `backend/app/main.py`: `GET /me` y `GET /accounts`. Consultan la API REST de Supabase con la clave anon y el JWT del usuario, sin `service_role`; `/accounts` no filtra por usuario, el aislamiento lo hace RLS (D4).
  - `backend/app/config.py` y `.env.example`: `SUPABASE_URL`, `SUPABASE_ANON_KEY`. `requirements.txt`: `pyjwt[crypto]`.
  - `backend/tests/test_auth.py`: 12 tests sin red (válido, sin token, firma inválida, caducado, audiencia incorrecta, emisor incorrecto, alg HS256, alg none, malformado, alg no permitido sin descargar el JWKS, rotación de `kid`, una sola recarga).
  - `backend/tests/test_api_two_users.py`: A y B vía API contra Supabase local (solo corre si la URL es local), contraseña de 7 caracteres → `weak_password`, correo sin confirmar → `email_not_confirmed`.
  - `.github/workflows/db.yml`: también se activa con `backend/**`, ya no excluye mailpit, corre pytest con `REQUIRE_SUPABASE=1`.
- Nube:
  - JWKS público del proyecto `hztlemmvferfogybwlsd` → HTTP 200, una clave `ES256` (EC P-256); consulta autorizada por el supervisor.
  - Contraseña mínima de 8 y confirmación de correo: **configuradas a mano por el supervisor en el panel** (sin `config push`; no verificado por el agente).
- Verificación:
  - `ruff check backend` → All checks passed
  - Con Supabase local: `pytest backend -v` → 16 passed; sin Supabase local → 13 passed, 3 skipped; sin Supabase local y con `REQUIRE_SUPABASE=1` → error (no hay falso verde).
  - CI → CI success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45496603951 · DB success (supabase test db + "Pruebas de integración del backend") https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45496603987
  - `npx supabase stop` → 0 contenedores.
- Commits: e3282bc, bcc842b, ff77ea8, dbf3311, ab64bf2, 5519729
- Pendientes:
  - Paso 07: inicio de sesión con Google (necesita un cliente OAuth de Google y activar el proveedor en Supabase) y acceso biométrico, ambos desde la app.
  - Paso 16: prueba de dos usuarios contra la nube (no se crearon usuarios en la nube, por decisión del supervisor).
- Riesgos: el JWKS se guarda en memoria sin caducidad; las claves nuevas se recogen por la recarga ante un `kid` desconocido, pero una clave revocada seguiría aceptándose hasta reiniciar el backend. El límite local de correos (`[auth.rate_limit] email_sent`) puede frenar ejecuciones repetidas del test de correo sin confirmar.
- Siguiente: Paso 07 — Auth en la app (no iniciado)

## 2026-11-24 · Paso 05 (cierre) — Verificación en la nube y CI de base de datos
- RQ: RQN 01, RQN 03
- Nube: el supervisor aplicó la migración con `npx supabase db push` en el proyecto `hztlemmvferfogybwlsd`.
- Cambios: `.github/workflows/db.yml` (nuevo): tarea `db`, se activa solo cuando cambia `supabase/**`; ejecuta CLI 3.3.0 → `supabase start` (solo db + auth) → `supabase test db`.
- Verificación:
  - `npx supabase test db --remote --yes` → NO ejecutable: la CLI instala pgtap temporalmente y su rol de login no encuentra `plan(integer)` (en `pg_extension` del proyecto no queda pgtap). No se cambiaron permisos en producción.
  - Alternativa, `npx supabase db query --remote` (solo lectura) → RLS `true` en accounts, budgets, categories, pocket_movements, pockets, profiles, transactions; `numeric(14,2)` en budgets.amount, pocket_movements.amount, pockets.target_amount, transactions.amount; 6 categorías globales (Alimentos, Entretenimiento, Otros, Salud, Servicios, Transporte); migración `20261124035811 init_schema` registrada.
  - CI → CI: success https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45485274816 · DB: success (`supabase start` y `supabase test db` en verde) https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45485274829
  - `npx supabase stop` → 0 contenedores de Supabase en marcha.
- Commits: 21ea2be (migración + tests), 8a871df (tarea db)
- Pendientes para pasos futuros:
  - Paso 06: exigir contraseña mínima de 8 caracteres (hoy `minimum_password_length = 6` en `supabase/config.toml` y el valor por defecto en el proyecto de la nube).
  - Paso 11: validar que un retiro de bolsillo no deje lo apartado en negativo (hoy `pocket_movements` solo exige amount ≠ 0).
  - Paso 11: contar los días del presupuesto en hora de Colombia (America/Bogota), no en UTC.
- Riesgos: los 27 tests de RLS se ejecutan en local y en la CI, pero no contra la nube; allí solo se verificó la estructura.
- Siguiente: Paso 06 — Auth backend (no iniciado)

## 2026-11-24 · Paso 05 — Modelo de datos en Supabase (luego cerrado, ver entrada superior)
- RQ: RQN 03 (montos NUMERIC(14,2), sin saldos guardados), RQN 01 (RLS en las 7 tablas; FKs compuestas)
- Decisiones: D3, D4, D5 en `docs/CONTEXT.md`
- Cambios: `supabase/config.toml` + `supabase/.gitignore` (`supabase init`); `supabase/migrations/20261124035811_init_schema.sql`:
  - tablas `profiles` (trigger al registrarse en `auth.users`), `accounts`, `categories` (6 globales sembradas), `transactions`, `budgets`, `pockets`, `pocket_movements`;
  - CHECK en kind, direction, source, status, last4 y montos; UNIQUE NULLS NOT DISTINCT (user_id, name) en categories; índice único parcial (user_id, source_ref);
  - FK compuestas (account_id, user_id) → accounts y (pocket_id, user_id) → pockets; exclusión de periodos solapados en budgets (btree_gist);
  - políticas: solo filas propias; en transactions, insert/update solo con categorías globales o propias.
  - `supabase/tests/rls_test.sql` (pgTAP, 27 pruebas con usuarios A y B).
- Verificación (stack local en Docker, mismas migraciones que irán a la nube):
  - `npx supabase db reset` → Applying migration 20261124035811_init_schema.sql… Finished
  - `npx supabase test db` → Files=1, Tests=27, Result: PASS
  - Consulta: tablas de `public` sin RLS = 0; columnas de monto que no son numeric = 0
- Commit: 21ea2be
- Pendientes/riesgos: falta `supabase link` + `supabase db push` al proyecto en la nube (requiere `npx supabase login` del supervisor y el project ref). Los tests de BD no corren en la CI (solo en local). Las categorías globales sembradas (Servicios, Salud, Otros además de las 3 del documento) son una propuesta.
- Siguiente: aplicar en la nube → cerrar Paso 05 → Paso 06 (Auth backend)

## 2026-11-24 · Paso 04 (seguimiento) — Quitar el NDK fijado: NO aplicado
- Intento: volver a `ndkVersion = flutter.ndkVersion` (28.2.13676358).
- Verificación: `flutter build apk --debug` → falla; Gradle vuelve a llamar a `sdkmanager` (0xC0000409). En `%LOCALAPPDATA%\Android\Sdk\ndk\` solo existe `30.0.16138531`; el 28.2 no se encuentra en esa ruta ni en otra.
- Decisión: se revierte el cambio (sin commit de una build rota); el NDK 30 sigue fijado.
- Siguiente: el supervisor confirma dónde se instaló el NDK 28.2 → reintentar.

## 2026-11-24 · Paso 04 (cierre) — Timeout de /health y prueba en emulador
- RQ: RQN 02 (corre en Android), RQN 05 (si el backend no responde, se muestra un mensaje claro en vez de quedarse cargando)
- Cambios: `app/lib/main.dart` (la llamada a `/health` se corta a los 5 s con `healthTimeout`); `app/test/health_test.dart` (tercer test: el backend no responde → "Backend no disponible"); `app/android/app/build.gradle.kts` (`ndkVersion` fijado al NDK instalado 30.0.16138531, porque Flutter pide 28.2.13676358 y su descarga vía sdkmanager falla)
- Verificación: `flutter analyze` → No issues found; `flutter test` → 3 passed; `flutter build apk --debug` → APK generada; `flutter run -d emulator-5554` (Android 17, API 37) con el backend en `0.0.0.0:8000` → el emulador muestra "Backend conectado" y el log del backend registra `GET /health 200` desde la app
- Commit: f5865f5
- Pendientes/riesgos: el NDK fijado depende de esta máquina (marcado `shortcut:` en el código). El emulador de API 37 perdió una vez su servicio `package` y hubo que reiniciarlo. iOS sigue sin probar (no hay Mac; hará falta una excepción de ATS para http).
- Siguiente: Paso 05 — Modelo de datos en Supabase

## 2026-11-23 · Paso 04 — Esqueleto Flutter (luego cerrado el 2026-11-24, ver entrada superior)
- RQ: RQN 02 (solo plataformas Android + iOS), RQN 05 (una sola pantalla con un mensaje)
- Cambios: `app/` creada con `flutter create --empty` (paquete `fsf_app`, org `co.finanzassinfiltro`) + dependencia `http`; `app/lib/main.dart` (pantalla que llama a `GET /health`; URL configurable con `--dart-define=API_URL`, por defecto `http://10.0.2.2:8000`); `app/test/health_test.dart` (2 widget tests con un cliente HTTP simulado); `app/android/app/src/debug/AndroidManifest.xml` (permite http solo en debug); `.github/workflows/ci.yml` (Flutter fijado en 3.47.2; pub get, analyze y test como pasos separados)
- Verificación: `flutter analyze` → No issues found; `flutter test` → 2 passed; CI → success con las 3 tareas ejecutando de verdad — https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45300603470
- Commits: b2c9e08, a85b447
- Bloqueos (entorno local, no código):
  - No hay ningún emulador Android creado (`flutter emulators` → ninguno).
  - Licencias del SDK de Android sin aceptar (`flutter doctor`).
  - `flutter build apk --debug` falla: Gradle llama a `sdkmanager` (ahora un envoltorio de "Android CLI") y este se cae con 0xC0000409. El Java del sistema es 1.8.
- Pendientes/riesgos: iOS no se puede probar (no hay Mac); en iOS el acceso por http necesitará una excepción de ATS. El primer run de la tarea `app` falló sin log público; se resolvió fijando la versión de Flutter (causa exacta no confirmada).
- Siguiente: cerrar el Paso 04 con la prueba en emulador → Paso 05 (Supabase)

## 2026-11-23 · Paso 03 — Esqueleto backend
- RQ: — (base técnica; habilita la tarea `backend` de la CI)
- Cambios: `backend/requirements.txt`, `backend/pyproject.toml` (pytest + ruff), `backend/.env.example`, `backend/app/{__init__,config,main}.py` (FastAPI con `GET /health` y configuración leída de `.env`), `backend/tests/test_health.py`
- Verificación: `ruff check` → All checks passed; `pytest backend` → 1 passed; `curl localhost:8765/health` → `{"status":"ok","env":"dev"}` HTTP 200; CI → success, y la tarea `backend` ejecutó ruff + pytest — https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45298815178
- Commit: db3da1f
- Pendientes/riesgos: aviso de deprecación de anyio dentro de starlette (dependencia, no afecta). Python 3.12 tanto en local (`backend/.venv`) como en la CI.
- Cómo arrancar: `cd backend && .venv/Scripts/uvicorn app.main:app --reload`
- Siguiente: Paso 04 — Esqueleto Flutter

## 2026-11-23 · Paso 02 — CI mínima
- RQ: RQN 01 (escaneo de secretos con gitleaks), RQN 03 (los tests de backend corren en cada push)
- Cambios: `.github/workflows/ci.yml` (nuevo). Tiene 3 jobs: `secrets` (gitleaks sobre todo el historial), `backend` (ruff + pytest, se activa cuando existe `backend/requirements.txt`) y `app` (flutter analyze + test, se activa cuando existe `app/pubspec.yaml`)
- Verificación: YAML válido; run #1 → success — https://github.com/ALEMN2481/fsf-zero-ui/actions/runs/45298111029
- Commit: 82b8af0
- Pendientes/riesgos: los jobs `backend` y `app` todavía no ejecutan nada (sus pasos se saltan); se validarán de verdad en los pasos 3 y 4. `gh` no tiene sesión iniciada en este equipo; consulto la API pública.
- Siguiente: Paso 03 — Esqueleto backend

## 2026-11-23 · Paso 01 — Base del repositorio
- RQ: RQN 01 (sin secretos ni herramientas locales en el repo)
- Cambios: `.gitignore`, `CLAUDE.md`, `docs/CONTEXT.md`, `docs/ROADMAP.md`, `docs/CHANGELOG.md` (nuevos); `README.md` (enlaces); `docs/` fuente (PDF + document.md)
- Verificación: `git ls-files` → 8 archivos, sin `markitdown/` ni `.serena/`; `git push origin main` → `a4e3477..8560b30`
- Commit: 8560b30 — https://github.com/ALEMN2481/fsf-zero-ui/commit/8560b30
- Pendientes/riesgos: el remoto pertenece a la cuenta ALEMN2481
- Siguiente: Paso 02 — CI mínima
