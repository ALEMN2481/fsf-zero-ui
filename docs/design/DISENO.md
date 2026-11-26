# Diseño de la app (Figma) — decisiones del supervisor

Fuente: archivo de Figma «Invest App App design (Community)», página **Screens**, exportado en PNG 2x en esta carpeta.
Es una plantilla de la Comunidad de Figma adaptada: **revisar su licencia** en la página del archivo y, si lo exige (p. ej. CC BY 4.0), dar crédito al autor en el README.

Regla general: de la plantilla se toma el **estilo**; las pantallas se adaptan a las decisiones del proyecto (CONTEXT.md, D1–D13) y a RQN 05 (Zero-UI). Si algo del diseño choca con una decisión aprobada, **gana la decisión** y se avisa al supervisor.

## Qué es cada imagen

| Imagen | Qué es | Paso | Uso |
|---|---|---|---|
| `logo.png` | **Logo oficial** (círculo discontinuo con «$»), sobre fondo blanco | 7, 12 y donde haga falta | Ícono de la app (Android/iOS), acceso, arranque |
| `Finanzas Sin Filtro · Launch.png` | Pantalla de arranque oscura | 7 | Sí, **cambiando el escudo por el logo oficial** |
| `user-login-auth.png` | Acceso | 7 | Sí, con ajustes (ver abajo) |
| `Primer vistazo · Tutorial del dashboard.png` | Tutorial superpuesto sobre la principal | 12 | Sí, con ajustes |
| `screen-dashboard.png` | Principal | 12 | **Solo el estilo** (sin gráfico) |
| `Categorizar gasto.png` | Hoja inferior de categoría | 12 | Sí |
| `savings-pockets-budgets.png` | Mis bolsillos | 12 | Sí |
| `screen-chatbot.png` | Chat del Coach | 13 | Sí, con ajustes (en el Paso 13) |
| `Fuentes de Datos.png` | Fuentes de datos | 8 / ajustes | Sí, adaptada (ver abajo) |
| `image 11.png`, `image 12.png` | Maquetas promocionales de la plantilla | — | Solo referencia de estilo |
| `image 10.png`, `image 13.png` | Logos alternativos | — | **No se usan** |
| `notification.png`, `Contact info edit.png` | Restos de la plantilla de inversiones | — | **No se usan** |
| `Splash screen.png` | Exportación vacía (blanco) | — | Ignorar |

## Decisiones (aprobadas por el usuario)

1. **Sin gráficos en la principal.** El gráfico de barras «Weekly velocity» no se implementa (RQN 05; el test del Paso 12 que prohíbe gráficos se mantiene). De `screen-dashboard` se toma solo el estilo.
2. **Fuentes de Datos adaptada a D7:** una tarjeta «Conectar Gmail» con su estado (conectado / reconectar). Nada de dirección de reenvío ni «Conexión bancaria directa» (fuera de alcance). Texto honesto en lugar de «cifrado militar TLS 1.3», p. ej. «Tus datos viajan y se guardan cifrados».
3. **Sin «Continuar con Apple»** (exige cuenta de desarrollador de Apple y Mac).
4. **Acceso:** se mantiene correo + contraseña (Paso 7), con el estilo del diseño: el correo primero y la contraseña en el mismo formulario o en un segundo paso, como máximo 3 campos. El acceso sin contraseña (enlace o código por correo) queda como mejora futura.
5. **Tutorial:** «Obligaciones» se quita (el motor no lo calcula); «Reservado» = lo apartado en bolsillos; la cifra grande es la del Paso 12 («Saldo libre para hoy» / «Hoy puedes gastar»).
6. **Coach (Paso 13):** no muestra métricas que el motor no calcula (p. ej. el «safety index» del diseño). Solo cifras del backend.
7. **Logo oficial:** `logo.png` (antes «ChatGPT Image 16 sept 2026, 20_37_27 1.png»; el fondo transparente se compuso sobre blanco), en el ícono de la app (Android e iOS, con `flutter_launcher_icons`), en el acceso y en el arranque (sobre una placa blanca, porque el arranque es oscuro). En la app: `app/assets/images/logo.png`.

## Correcciones para todas las pantallas

- Textos **en español** («Liquid balance», «Ledger», «View all» y el chat están en inglés).
- Montos en **formato colombiano** con el formateador sin `double` del Paso 12: `$ 4.250.000`, no `$4,250.00`.
- Solo **categorías reales** de la app (p. ej. «Alimentos», no «Supermercado»).
- Datos de ejemplo de la plantilla («Sofía», «Warren Buffet»…) no van a la app.
- Se mantienen las reglas aprobadas: cifras desde el backend, accesibilidad con el texto al 200 %, botones de al menos 48×48 y contraste suficiente.

## Estilo a adoptar

- Monocromo: fondo blanco, tarjetas gris claro, texto negro, etiquetas en gris azulado.
- Botones principales negros en forma de píldora; secundarios gris claro.
- Esquinas muy redondeadas en tarjetas y botones.
- Tipografía de títulos ancha y gruesa para la cifra grande.
- Botón flotante negro con el destello (✦) para abrir el Coach (Paso 13).
- Colores, tipografías y medidas exactos: **`tokens.md`** (extraídos de Figma, con correcciones de contraste que mandan sobre el diseño).

## Estado de la implementación (Paso 12B, D14)

- Implementadas: arranque, acceso, principal (con la tarjeta «Reservado»), hoja «Categorizar gasto», bolsillos, tutorial «Primer vistazo» y Fuentes de Datos. Capturas en `app/test/goldens/` (golden tests) y en `docs/capturas/paso12b_*` (emulador).
- Decisiones del supervisor al implementar: tarjeta «Reservado» en la principal (total de los bolsillos, del backend); sin botón ni globo del Coach hasta el Paso 13; total y % de los bolsillos calculados en el backend; sin «Ingresar con FaceID» ni texto legal en el acceso (no hay documentos de Términos ni Privacidad todavía).
- Diferencias menores: los chips de categoría no llevan emojis; el botón «atrás» usa el estándar de Android (área de 48×48) en lugar del cuadrado gris; no hay enlace «Ajustes» en bolsillos (Fuentes de Datos está en el menú ⋮ de la principal).
- Paso 13 (D15): chat del Coach según `screen-chatbot` con los ajustes aprobados: cabecera «Coach» / «Tu coach financiero» con el círculo ✦; sin buscar, filtrar ni ajustes (un menú ⋮ con «Borrar conversación»); sin «safety index»; textos en español; cifras del backend en negrita; estado vacío con 3 preguntas sugeridas y el aviso «El Coach te explica tus cifras; no es asesoría financiera profesional». Botón flotante ✦ (60) en la principal y globo del Coach en el tutorial. Diferencias: fondo del chat blanco (no gris) y texto del campo en `#475569` (el gris tenue del diseño no llega a 4,5:1). Capturas: `app/test/goldens/11_coach.png`, `11b_coach_texto_200.png`, `12_coach_vacio.png` y `docs/capturas/paso13_coach_vs_diseno.png`.
- **Licencia de la plantilla de Figma: sin revisar** (el conector de Figma no está autorizado en esta sesión). Queda anotada en el ROADMAP para el supervisor.
