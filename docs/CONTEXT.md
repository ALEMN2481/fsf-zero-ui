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
                                     ├─ Ingesta: correo → servidor MCP → LLM → JSON validado (Pydantic)
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
