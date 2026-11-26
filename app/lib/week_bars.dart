import 'package:flutter/material.dart';

import 'money.dart';
import 'movements.dart' show bogota;
import 'theme.dart';

const _letters = ['L', 'M', 'M', 'J', 'V', 'S', 'D'];
const _names = ['lunes', 'martes', 'miércoles', 'jueves', 'viernes', 'sábado', 'domingo'];

/// Gasto de la semana (Paso 15B, D13): 7 barras negras de lunes a domingo con lo gastado cada día,
/// tal como lo calcula el backend (`/gps` → `semana_dias`). Es el único gráfico de la app (RQN 05):
/// sin librería de gráficas ni CustomPaint, solo contenedores. Para el lector de pantalla es un
/// solo texto con el monto de cada día hasta hoy; la letra de hoy va en negrita.
class WeekBars extends StatelessWidget {
  const WeekBars({super.key, required this.days, required this.now});

  /// [{fecha: "2026-11-23", gastado: "45900.00"}, …] de lunes a domingo.
  final List<Map<String, dynamic>> days;
  final DateTime now;

  static const barsHeight = 96.0;

  @override
  Widget build(BuildContext context) {
    final t = bogota(now);
    final today = '${t.year}-${t.month.toString().padLeft(2, '0')}-${t.day.toString().padLeft(2, '0')}';
    final amounts = [for (final d in days) cents(d['gastado'] as String)];
    final top = amounts.fold(BigInt.zero, (a, b) => b > a ? b : a);
    final spoken = [
      for (var i = 0; i < days.length; i++)
        if ((days[i]['fecha'] as String).compareTo(today) <= 0)
          '${_names[i]}${days[i]['fecha'] == today ? ' (hoy)' : ''}: ${formatCop(days[i]['gastado'] as String)}',
    ];
    return Semantics(
      container: true,
      label: 'Gasto de la semana. ${spoken.join('. ')}.',
      child: ExcludeSemantics(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            for (var i = 0; i < days.length; i++)
              Expanded(
                child: Column(
                  children: [
                    SizedBox(
                      height: barsHeight,
                      child: Center(
                        child: Container(
                          width: 20,
                          alignment: Alignment.bottomCenter,
                          decoration: const BoxDecoration(
                            color: Fsf.borde,
                            borderRadius: BorderRadius.all(Radius.circular(6)),
                          ),
                          // Alto proporcional al día que más se gastó (milésimas en BigInt: solo
                          // para dibujar; el dinero nunca pasa por double).
                          child: FractionallySizedBox(
                            heightFactor: top == BigInt.zero
                                ? 0
                                : (amounts[i] * BigInt.from(1000) ~/ top).toInt() / 1000,
                            widthFactor: 1,
                            child: Container(
                              key: ValueKey('barra_${days[i]['fecha']}'),
                              decoration: const BoxDecoration(
                                color: Fsf.primario,
                                borderRadius: BorderRadius.all(Radius.circular(6)),
                              ),
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(height: 6),
                    // Al 200 % la letra se reduce dentro de su columna en vez de desbordar.
                    SizedBox(
                      height: 20,
                      child: FittedBox(
                        child: Text(
                          _letters[i],
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: days[i]['fecha'] == today ? FontWeight.w800 : FontWeight.w400,
                            color: days[i]['fecha'] == today ? Fsf.texto : Fsf.textoSecundario,
                            decoration: days[i]['fecha'] == today ? TextDecoration.underline : null,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
          ],
        ),
      ),
    );
  }
}
