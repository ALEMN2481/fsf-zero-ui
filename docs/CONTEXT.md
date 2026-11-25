# Contexto — Finanzas Sin Filtro

Fuente: [Proyecto_Finanzas_ Completo.pdf](Proyecto_Finanzas_%20Completo.pdf) / [document.md](document.md) (secciones iniciales: idea, módulos, metodología, sprints, RQF/RQN).

## Visión
App móvil de finanzas personales Zero-UI: registra gastos automáticamente leyendo
notificaciones bancarias y facturas electrónicas del correo, calcula saldos de forma
determinista y aconseja en lenguaje simple mediante un Coach IA. Público: jóvenes con
ingresos recurrentes que no anotan gastos. Modelo B2C freemium.

## Módulos
1. **Autenticación y Perfil** — registro, login, verificación, metas de ahorro.
2. **Ingesta y Parsing (IA)** — lectura de correos/facturas → JSON (monto, comercio, fecha, medio de pago).
3. **Motor Financiero ("GPS")** — recálculo determinista de saldo libre y presupuesto diario/semanal.
4. **Coach Financiero** — chat y notificaciones en lenguaje simple.

## Arquitectura
```
Flutter (Android/iOS) ─HTTPS/JWT─▶ FastAPI (Python)
                                     ├─ Motor financiero (Decimal + SQL)
                                     ├─ Ingesta: correo → extracción (app/extract: reglas fijas y XML DIAN;
                                     │           LLM solo de respaldo → JSON validado con Pydantic)
                                     │  └─ Servidor MCP mínimo (demostración) sobre el mismo módulo (D9)
                                     └─ Coach: LLM recibe solo cifras ya calculadas
Supabase: PostgreSQL (fuente de verdad, RLS), Auth (email + OAuth), tokens OAuth cifrados.
Push: Firebase Cloud Messaging (confirmación de gasto y aclaración de parsing ambiguo).
```

Garantías:
- (a) El LLM no toca la BD de saldos ni hace aritmética.
- (b) El flujo correo → extracción → recálculo → UI funciona sin intervención del usuario.

## Requerimientos funcionales
| ID | Nombre | Prioridad | Criterio de aceptación resumido |
|---|---|---|---|
| RQF 01 | Autenticación y registro | Alta | Registro, login y verificación por credenciales u OAuth. |
| RQF 02 | Ingesta automática | Alta | De un correo bancario/factura se extraen monto, comercio, fecha y medio de pago. |
| RQF 03 | Categorización | Media | Cada gasto queda en una categoría simple (Alimentos, Transporte, Entretenimiento, Otros…). |
| RQF 04 | Saldo y Coach | Alta | Consulta instantánea del saldo libre + chat en lenguaje natural. |
| RQF 05 | Recálculo GPS | Alta | Un gasto fuera de plan recalcula el presupuesto diario y semanal. |

## Requerimientos no funcionales
| ID | Tipo | Criterio medible |
|---|---|---|
| RQN 01 | Seguridad y privacidad | HTTPS en todo; OAuth 2.0; datos sensibles cifrados; RLS por usuario; sin secretos en el repo. |
| RQN 02 | Multiplataforma | El mismo código Flutter compila y corre en Android e iOS. |
| RQN 03 | Precisión matemática | Saldos/presupuestos solo en código/BD con Decimal/NUMERIC; tests cubren cada fórmula. |
| RQN 04 | Tiempo de respuesta | Correo recibido → push de confirmación en < 10 s (medido). |
| RQN 05 | Zero-UI | Sin menús saturados, formularios largos, tablas ni gráficos recargados. |

## Mapa sprint → pasos
- Sprint 1 (T1.1–T1.4) → Pasos 1–7
- Sprint 2 (T2.1–T2.3) → Pasos 8–10
- Sprint 3 (T3.1–T3.3) → Pasos 11–12
- Sprint 4 (T4.1–T4.3) → Pasos 13–16

## Decisiones
- D1 (2026-11-23): Supabase (PostgreSQL + Auth) como BD; Firebase solo para FCM.
- D2 (2026-11-23): El LLM se usa únicamente para extracción JSON y redacción del Coach.
- D3 (2026-11-24): Supabase en la nube (no local). Migraciones versionadas en `supabase/migrations/` con la CLI de Supabase. Montos en NUMERIC. RLS activado en todas las tablas. La clave `service_role` vive solo en `backend/.env` (nunca en la app ni en el repo).
- D4 (2026-11-24): El backend reenvía el JWT del usuario en sus consultas a Supabase, así RLS se aplica también desde el backend. La `service_role` se usa solo en procesos sin usuario (p. ej. la ingesta del Paso 8).
- D5 (2026-11-24): Solo COP en el MVP; una compra en otra moneda queda `pending_review`. Los ingresos son `transactions` con `direction='income'`. Bolsillos: tabla `pocket_movements` (monto con signo); lo apartado es la suma de sus movimientos, no una columna.
- D6 (2026-11-24): La app habla con Supabase Auth mediante `supabase_flutter` (flujo PKCE). La sesión se guarda cifrada con `flutter_secure_storage` (Keystore/Keychain), nunca en SharedPreferences. Enlace de vuelta a la app: `co.finanzassinfiltro.fsfapp://login-callback` (confirmación de correo y Google). Bloqueo local con `local_auth`: al abrir y tras ≥ 5 min en segundo plano; acepta el PIN del dispositivo; sin biometría ni PIN no bloquea y avisa una vez.
- D7 (2026-11-25): Recepción de correos por **Gmail API con `gmail.readonly` + `users.watch` y Pub/Sub** (opción A del Paso 08). Conexión con OAuth propio del backend y permiso incremental (el login de Supabase sigue con `openid email profile`; `gmail.readonly` se pide solo al pulsar "Conectar Gmail", con `access_type=offline` e intercambio del código en el backend). El `refresh_token` se guarda cifrado; ante `invalid_grant` la conexión queda `needs_reconnect` sin reintentos. Solo se confía en el `Authentication-Results` de `mx.google.com` situado arriba de todo y el dominio firmante debe coincidir con el de la regla. Los correos se guardan cifrados (AES-256-GCM con versión de clave) en `inbound_emails`. Mientras la app esté "En pruebas" (≤ 100 usuarios) no hace falta la evaluación CASA. **Plan de salida:** si al publicar la evaluación CASA resulta inviable, pasar a la opción B (reenvío por filtro a una dirección por usuario + servicio de correo entrante con webhook firmado); `inbound_emails` ya admite `source = 'forward'`.
- D8 (2026-11-25): Carpetas de Gmail. Los avisos (`users.watch`) y la lectura del historial cubren **todo el buzón**; antes de descargar un correo se miran sus etiquetas actuales: las reglas de **bancos** se aceptan desde `INBOX` y `SPAM` (el DKIM del dominio del banco frena la suplantación); la de **facturas electrónicas** solo desde `INBOX` (el phishing con "facturas" y `.zip` maliciosos es común y puede tener DKIM válido de su propio dominio; si Gmail la manda a Spam, se descarta); `SENT`, `DRAFT` y `TRASH` siempre se descartan, igual que los archivados (sin `INBOX` ni `SPAM`).
- D9 (2026-11-25): La extracción es un **módulo dentro del backend** (`app/extract/`), llamado por el propio flujo del correo: facturas por lectura determinista del XML UBL de la DIAN, alertas bancarias por reglas fijas y el LLM solo como respaldo con esquema Pydantic estricto. MCP no aporta al camino del correo (el flujo lo decide el código, no un agente) y sumaría proceso, transporte y latencia con RQN 04 en el límite. Como el documento del proyecto lo exige (arquitectura, CU-02/CU-03 y criterio de evaluación), se expondrá **un servidor MCP mínimo para la demostración** que envuelve ese mismo módulo, fuera del camino del correo.
