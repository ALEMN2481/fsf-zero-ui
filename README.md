# fsf-zero-ui
Zero-UI/Low-UI personal finance mobile app that automates expense tracking by reading bank notifications and electronic invoices, featuring deterministic financial calculations and a conversational AI coach.

## Documentación
- [CLAUDE.md](CLAUDE.md) — reglas de trabajo
- [docs/CONTEXT.md](docs/CONTEXT.md) — visión, arquitectura y requerimientos
- [docs/ROADMAP.md](docs/ROADMAP.md) — ruta paso a paso y estado
- [docs/CHANGELOG.md](docs/CHANGELOG.md) — bitácora de entregas
- [docs/](docs/) — documento fuente del proyecto (PDF)

## Servidor MCP de demostración (extracción)
Servidor MCP mínimo por **stdio** ([backend/app/mcp_server.py](backend/app/mcp_server.py), decisión D9).
Expone dos herramientas y solo procesa el texto que recibe: no usa la base de datos, no lee
`backend/.env` ni ningún secreto, y su única red es un Ollama local (cualquier otra `OLLAMA_URL`
desactiva el LLM). Está fuera del camino real del correo.

| Herramienta | Entrada | Devuelve |
|---|---|---|
| `extract_bank_alert` | `text` (alerta de Bancolombia), `received_at` opcional (ISO 8601) | `status` (`confirmed`, `pending_review` o `no_movement`), `source` (`plantilla` o `llm`) y los campos extraídos. Lo que viene del LLM siempre es `pending_review`. |
| `parse_amount` | `text` (p. ej. `$1.234.567,89`) | `amount` con 2 decimales; error si no es un monto válido en COP |

Probarlo con [MCP Inspector](https://github.com/modelcontextprotocol/inspector) (requiere Node.js), desde `backend/`:

```bash
cd backend
# Windows
npx @modelcontextprotocol/inspector .venv/Scripts/python.exe -m app.mcp_server
# macOS / Linux
npx @modelcontextprotocol/inspector .venv/bin/python -m app.mcp_server
```

Se abre la interfaz web del Inspector con el transporte stdio ya configurado: en **Tools → List Tools**
aparecen las dos herramientas; prueba `extract_bank_alert` con, por ejemplo,
`Bancolombia: Compraste $23.500,00 en PANADERIA EJEMPLO con tu T.Deb *0000, el 23/11/2026 a las 07:45.`
Para el respaldo con LLM hace falta Ollama en marcha con `qwen2.5:3b` (`ollama pull qwen2.5:3b`);
la primera llamada con el modelo fuera de memoria tarda ~12–14 s.

## Créditos de diseño
- Tipografías **Inter** (The Inter Project Authors) y **Unbounded** (The Unbounded Project Authors), con licencia SIL Open Font License 1.1: `app/assets/fonts/*/OFL.txt`.
- Estilo visual adaptado de la plantilla «Invest App App design (Community)» de la Comunidad de Figma. *Licencia pendiente de revisar por el supervisor (ver ROADMAP); si exige atribución, se añadirá aquí.*
- Logo: `docs/design/logo.png`.
- Logo «G» de Google en «Continuar con Google»: recurso oficial de las normas de marca de *Sign in with Google* (tema «Neutral»), sin modificar (`app/assets/images/google_g.png`).
