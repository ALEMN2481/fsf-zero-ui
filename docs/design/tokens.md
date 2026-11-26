# Tokens de diseño (extraídos de Figma)

Fuente: archivo de Figma «Invest App App design (Community)», página **Screens**, leído con el conector de Figma (solo lectura). El archivo **no tiene variables** definidas: estos valores salen de las capas de cada pantalla.
Pantallas leídas: `screen-dashboard` (342:8), `user-login-auth` (348:10), `savings-pockets-budgets` (354:10), `Categorizar gasto` → hoja (379:105) y `Finanzas Sin Filtro · Launch` (392:25).
Se aplican con las decisiones de `DISENO.md`. Los ajustes de accesibilidad de abajo **mandan** sobre el valor original de Figma.

## Tipografía

El diseño mezcla tres familias: **Unbounded** (cifras y títulos), **Geist** (texto en principal y bolsillos) e **Inter** (acceso, hoja de categoría y arranque). Para la app:

| Uso | Familia | Peso | Tamaño | Notas |
|---|---|---|---|---|
| Cifra grande (disponible hoy, total de bolsillos) | Unbounded | Medium (500) | 40 | Envolver en `FittedBox`: Unbounded es muy ancha y con el texto al 200 % debe reducirse, no desbordar |
| Títulos de sección («Últimos movimientos», «Metas de ahorro») | Unbounded | Bold (700) | 16 | |
| Montos en tarjetas | Unbounded | Bold (700) | 14 | |
| Etiqueta superior («HOY PUEDES GASTAR», «MIS BOLSILLOS») | Inter | SemiBold (600) | 14 | MAYÚSCULAS, color secundario |
| Texto principal de tarjeta (comercio, nombre del bolsillo) | Inter | SemiBold (600) | 16 | |
| Texto secundario (categoría, fecha) | Inter | Regular (400) | 12 | Color secundario |
| Título de marca (acceso, arranque) | Inter | Bold (700) | 32 (acceso) · 30 (arranque) | |
| Subtítulo de marca | Inter | Medium (500) | 16 · altura de línea 24 | |
| Pregunta de la hoja («¿A qué categoría…?») | Inter | Bold (700) | 26 · altura de línea 1.2 | |
| Monto + comercio en la hoja | Inter | Bold (700) | 38 · altura de línea 1.12 | |
| Botón principal | Inter | Bold (700) | 16 | |
| Botón secundario / chip | Inter | SemiBold (600) | 15 | |
| Texto legal / ayuda | Inter | Regular (400) | **12** | Figma usa 11 y 10: **subir a 12** (legibilidad) |

- **Geist se sustituye por Inter**: son muy parecidas y así la app usa solo dos familias.
- Las fuentes se **empaquetan en la app** (`assets/fonts/`, declaradas en `pubspec.yaml`), no se descargan en tiempo de ejecución. Unbounded e Inter tienen licencia SIL OFL (Google Fonts): incluir el archivo `OFL.txt` de cada una.

## Colores

| Token | Valor | Uso en Figma |
|---|---|---|
| `fondo` | `#FFFFFF` | Fondo de todas las pantallas claras |
| `superficie` | `#F1F5F9` | Tarjetas, campos de texto, botones secundarios, chips (Figma usa también `#F3F3F3` en la hoja: unificar a `#F1F5F9`) |
| `texto` | `#000000` | Texto principal, cifras (Figma usa también `#161616` en la hoja: se acepta) |
| `texto-secundario` | `#64748B` | Etiquetas y texto secundario **sobre fondo blanco** |
| `texto-secundario-en-superficie` | `#475569` | Texto secundario **sobre `#F1F5F9`** (ver accesibilidad) |
| `texto-tenue` | `#94A3B8` | **Solo** marcadores de posición (placeholder) de campos |
| `borde` | `#E2E8F0` | Divisores, borde del botón secundario, pista de la barra de progreso |
| `primario` | `#000000` | Botón principal, botón flotante, relleno de la barra de progreso |
| `sobre-primario` | `#FFFFFF` | Texto e iconos sobre negro |
| `asa-hoja` | `#D3D3D3` | Asa de arrastre de la hoja inferior |
| `arranque-fondo` | `#0D0D11` | Fondo de la pantalla de arranque |
| `arranque-texto-secundario` | `#A6A6AE` | Lema y estado en el arranque |
| `arranque-pista` | `#29292F` | Pista de la barra de carga del arranque |

Sin colores de alarma (rojo/verde) para montos: el signo y el texto bastan (decisión del Paso 12).

## Accesibilidad: correcciones sobre Figma (contraste WCAG AA, 4,5:1 para texto normal)

| Combinación en Figma | Contraste | Decisión |
|---|---|---|
| `#64748B` sobre blanco | 4,76 | ✅ Se usa |
| `#64748B` sobre `#F1F5F9` (categoría/fecha dentro de tarjetas) | **4,34** | ❌ Cambiar a `#475569` (6,92) |
| `#94A3B8` sobre blanco (texto legal, «o continúa con») | **2,56** | ❌ Cambiar a `#64748B`; `#94A3B8` solo en placeholders |
| `#777777` sobre blanco («Descartar / No es mi gasto») | **4,48** | ❌ Cambiar a `#64748B` |
| `#A6A6AE` sobre `#0D0D11` (arranque) | 8,02 | ✅ |
| `#000000` sobre `#F1F5F9` | 19,17 | ✅ |

## Formas y medidas

| Elemento | Medida |
|---|---|
| Margen lateral de pantalla | 24 (principal, acceso, bolsillos) · 28 (hoja, Fuentes de Datos): usar **24** en toda la app |
| Separación entre tarjetas | 8 (movimientos) · 12 (bolsillos, chips, botones) |
| Relleno interno de tarjeta | 16 |
| Radio de tarjeta de movimiento | 16 |
| Radio de tarjeta de bolsillo / tarjeta informativa | 20 |
| Campo de texto | alto 56 · radio 16 · relleno horizontal 16 |
| Botón principal | alto 60 · píldora (radio 30) · negro |
| Botón secundario (Google) | alto 56 · píldora (radio 28) · `#F1F5F9` |
| Chip de categoría | alto 64 · píldora · `#F1F5F9` · dos por fila |
| Botón «atrás» | 36×36 · radio 12 · `#F1F5F9` → **llevar el área táctil a 48×48** |
| Botón flotante (Coach ✦ / crear bolsillo +) | 60×60 · radio 28 · negro |
| Hoja inferior | radio superior 32 · asa 36×4 |
| Barra de progreso | alto 8 · radio 4 · pista `#E2E8F0` · relleno negro |

## Formato de cifras

Figma muestra `$4,250.00` y `$120.38` (formato de EE. UU.). En la app, siempre el formateador sin `double` del Paso 12: `$ 4.250.000` (punto de miles, sin `,00`).
