# Muestras del supervisor (simuladas)

Conjunto de prueba **independiente**, escrito por el supervisor y no por quien programa el parser.
Todo es inventado: no hay datos personales ni correos reales.

- `alertas.txt`: 16 alertas de Bancolombia (A01–A16), en formato nuevo ("Compraste…") y antiguo ("le informa…").
  **Los formatos son aproximados de memoria y no están confirmados contra alertas reales.**
- `F01`–`F06`: facturas electrónicas DIAN simuladas (`.zip` con `AttachedDocument` + PDF de relleno que no se debe leer).
  Firma XAdES simulada (no válida), CUFE = SHA-384 de un texto fijo.
- `esperado.json`: resultado esperado de cada alerta y factura. Gmail conectado simulado: `cliente.ejemplo@gmail.com`.
  Los casos con `"status": "DECISION"` (A05 retiro, A11 pago de la tarjeta, A14 avance) los decide el usuario antes de fijarlos.

Reglas para quien desarrolla:
- No modificar estos archivos para que pasen los tests. Si un esperado parece incorrecto, reportarlo al supervisor.
- Las muestras propias del desarrollador van en otra carpeta.
