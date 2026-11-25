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

## Motor financiero GPS (Paso 11, D12)
Código: `backend/app/engine/gps.py` (funciones puras con Decimal; la fecha de hoy entra como
parámetro). Días en hora de Colombia (`America/Bogota`). Montos en el JSON como texto.

**Datos de entrada** (periodo activo = el presupuesto `[ini, fin]` que contiene hoy, monto `P`):
- `Gasto(días)` = Σ gastos (`expense`, `confirmed` **o** `pending_review`) − Σ devoluciones
  **confirmadas** en esos días. Devolución = ingreso cuya categoría no es Ingresos.
- **No entran en `Gasto`**: ingresos (categoría Ingresos; se muestran aparte como información),
  devoluciones en revisión, facturas en efectivo (`counts_in_budget = false`: el dinero ya salió
  con el retiro en cajero, que es gasto; quedan en el detalle por categoría como
  `efectivo_factura`) y transferencias a una cuenta registrada del usuario (`to_last4` ∈ sus
  `accounts.last4`).
- `Ap` = Σ `pocket_movements` del periodo (+ apartar, − retirar).
- Un movimiento fechado después de hoy (dentro del periodo) cuenta como de hoy.

**Fórmulas**
| Cifra | Fórmula |
|---|---|
| Saldo al empezar hoy | `L₀ = P − Gasto(ini..ayer) − Ap` |
| Gastado hoy | `Gh = Gasto(hoy..fin)` |
| Saldo libre | `L = L₀ − Gh` |
| Días restantes | `n = fin − hoy + 1` (incluye hoy) |
| Reparto | `reparto(X, n)`: si `X ≤ 0`, n ceros; si no, `base = ⌊X⌋ // n` en pesos enteros, cuotas `[base]×(n−1)` y la última `X − base·(n−1)` (el sobrante de pesos y centavos va al último día; Σ = X exacto, sin redondeo) |
| Cuota de hoy | `cuota_hoy = reparto(L₀, n)[0]` |
| Disponible hoy | `cuota_hoy − Gh` (puede ser **negativo**) |
| Exceso (gasto fuera de plan) | `max(Gh − cuota_hoy, 0)` |
| Diario desde mañana (recálculo GPS) | `reparto(L, n − 1)[0]`; `null` el último día |
| Diario según el plan | `reparto(L₀ − cuota_hoy, n − 1)[0]` (para mostrar «baja de X a Y») |
| Disponible de la semana | `Σ reparto(L₀, n)[0:k] − Gh`, `k = min(domingo, fin) − hoy + 1` (semana lunes–domingo recortada al periodo) |
| Máximo apartable en un bolsillo | `max(L, 0)` |
| En revisión | Σ gastos `pending_review` del periodo (ya incluidos en `Gasto`) |
| Gasto por categoría | Σ gastos − Σ devoluciones confirmadas de la categoría (puede ser negativo); aparte, `efectivo_factura` |

Invariantes con tests de propiedades: Σ cuotas = L₀ (si L₀ > 0); `cuota_hoy · n ≤ L₀`; lo
disponible de la semana nunca supera L₀; Σ gasto por categoría = `Gasto` del periodo; un gasto
más nunca aumenta ninguna cifra y una devolución más nunca la reduce.

Sin presupuesto que contenga hoy → `estado: "sin_presupuesto"`, sin cifras. Un bolsillo nunca
queda en negativo (trigger en la BD); apartar más que `L` → 409 con el máximo posible.

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
- D10 (2026-11-25): El LLM de respaldo de la extracción es **local, con Ollama** (el texto del correo no sale del servidor). El modelo se elige midiendo con `backend/scripts/eval_llm.py`; hoy `qwen2.5:3b` sin ejemplos en el prompt, temperatura 0, salida forzada al esquema JSON. El backend lo precarga al arrancar y lo mantiene en memoria con `keep_alive` (`OLLAMA_KEEP_ALIVE`, 30m por defecto). Implica que el servidor de producción (Paso 16) necesita Ollama, idealmente con GPU.
- D11 (2026-11-25): **Categorización** (Paso 10). En línea y sin LLM, al insertar el movimiento: (1) ingreso → global **Ingresos** por la dirección, salvo las **devoluciones** (plantilla `devolucion`), que se categorizan por el comercio como un gasto para que en el Paso 11 resten de su categoría; (2) **regla propia del usuario** (`category_rules`, aprendida al corregir con `PATCH /transactions/{id}/category`, con RLS); (3) **reglas globales** de `backend/app/categorize/rules.toml` si el comercio encaja en una sola categoría; (4) si no, **Otros** con `category_source='pendiente'`. Un hilo de fondo pasa los pendientes por el **LLM local** (D10), que solo ve el nombre del comercio y elige entre las categorías del usuario (globales y propias, sin Ingresos) mediante un `enum` en el esquema; si duda, responde Otros, y si la respuesta no es válida, queda Otros. El LLM **solo escribe si `category_source` sigue en 'pendiente'** (condición en la misma escritura): nunca pisa una corrección del usuario. La latencia del aviso no depende del LLM. Limitación conocida: las reglas aprendidas comparan el comercio exacto normalizado (`EXITO CALLE 80` ≠ `EXITO LAURELES`); la corrección no recategoriza el historial.
- D12 (2026-11-25): **Motor financiero GPS** (Paso 11; fórmulas en §Motor financiero GPS). (1) El saldo libre se mide **contra el presupuesto del periodo**, no contra el saldo del banco (no hay saldo inicial ni las alertas lo traen); los ingresos no lo suben (el presupuesto ya es el plan que se paga con ellos). (2) Cuando se pasa, lo disponible se muestra **negativo**, con el exceso aparte. (3) Los gastos en revisión **cuentan** y las devoluciones en revisión **no** (más vale subestimar lo disponible), con `en_revision` aparte. (4) Semana de **lunes a domingo** recortada al periodo. (5) Las facturas en efectivo no suman al gasto (`counts_in_budget = false`): el retiro en cajero ya contó. (6) Una transferencia a unos 4 dígitos de una cuenta registrada del usuario es entre cuentas propias y no es gasto. (7) El cálculo es en Python (funciones puras) a partir de los datos en cada consulta: el recálculo ante un gasto fuera de plan ocurre solo. En la BD solo va la protección de los bolsillos (trigger).
- D13 (2026-11-25): **Pantalla «Disponible diario»** (Paso 12). (1) El presupuesto es del **mes calendario** y se renueva solo con el mismo monto: si ningún periodo contiene hoy, `/gps` usa el último monto para el mes en curso sin escribir nada (`periodo.renovado`). (2) La cifra propuesta es **el gasto del mes anterior** (nunca el 100 % de los ingresos); los ingresos se muestran solo como referencia. (3) «No es un gasto mío» deja el movimiento en `status = 'dismissed'` (no se borra; el motor y la lista lo excluyen). (4) La app refresca por **Supabase Realtime** (solo como señal, con RLS) y al volver a primer plano; las cifras siempre vienen del backend. (5) Montos en la app como **texto**: se formatean sin double ni `NumberFormat`. (6) Privacidad: `FLAG_SECURE` solo en release (en debug impediría las capturas de prueba) y una capa que tapa la app fuera de primer plano.
