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
