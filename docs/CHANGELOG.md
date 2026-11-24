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
