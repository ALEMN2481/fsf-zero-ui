import 'package:flutter/material.dart';

import 'home_screen.dart' show ReservedCard;
import 'money.dart';
import 'theme.dart';
import 'week_bars.dart';

/// «Primer vistazo» (D14): se muestra una vez sobre la principal. Usa las cifras reales del
/// backend; sin «Obligaciones» (el motor no las calcula). Paso 15B: el Coach está en la cabecera,
/// el gráfico de la semana y el botón «+» para agregar un gasto en efectivo.
class TutorialOverlay extends StatelessWidget {
  const TutorialOverlay({super.key, required this.gps, required this.onDone, this.now = DateTime.now});

  final Map<String, dynamic> gps;
  final VoidCallback onDone;
  final DateTime Function() now;

  @override
  Widget build(BuildContext context) {
    final today = gps['disponible_hoy'] as String;
    final week = (gps['semana_dias'] as List?)?.cast<Map<String, dynamic>>();
    return Material(
      color: const Color(0xFFD9D9D9),
      child: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(Fsf.margen),
          children: [
            Wrap(
              alignment: WrapAlignment.spaceBetween,
              crossAxisAlignment: WrapCrossAlignment.center,
              spacing: 12,
              children: [
                const Text('Inicio', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 24)),
                TextButton(onPressed: onDone, child: const Text('Omitir tutorial')),
              ],
            ),
            const SizedBox(height: 8),
            // Réplica de la burbuja derecha de la cabecera: ✦ Coach, bolsillos y ajustes.
            const Align(
              alignment: Alignment.centerRight,
              child: ExcludeSemantics(
                child: DecoratedBox(
                  decoration: BoxDecoration(color: Fsf.superficie, borderRadius: BorderRadius.all(Radius.circular(28))),
                  child: Padding(
                    padding: EdgeInsets.symmetric(horizontal: 12, vertical: 12),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.auto_awesome),
                        SizedBox(width: 24),
                        Icon(Icons.savings_outlined),
                        SizedBox(width: 24),
                        Icon(Icons.settings_outlined),
                      ],
                    ),
                  ),
                ),
              ),
            ),
            const _Bubble(
              arrowUp: true,
              arrowRight: true,
              text:
                  'Arriba a la derecha está tu Coach (✦): te explica tus cifras en palabras simples. '
                  'Al lado, tus bolsillos y los ajustes.',
            ),
            const SizedBox(height: 16),
            FittedBox(
              fit: BoxFit.scaleDown,
              alignment: Alignment.centerLeft,
              child: Text(formatCop(today), style: Fsf.cifra.copyWith(fontSize: 48)),
            ),
            const Text('Hoy puedes gastar', style: TextStyle(fontSize: 16)),
            const _Bubble(
              arrowUp: true,
              text:
                  'Aquí ves cuánto puedes gastar hoy sin salirte de tu presupuesto. Se actualiza solo '
                  'cuando llega un gasto a tu correo.',
            ),
            if (week != null && week.length == 7) ...[
              const SizedBox(height: 16),
              ExcludeSemantics(
                child: WeekBars(days: week, now: now()),
              ),
              const _Bubble(
                arrowUp: true,
                text: 'Cada barra es lo que gastaste ese día, de lunes a domingo. La letra de hoy va marcada.',
              ),
            ],
            const SizedBox(height: 16),
            if (gps['reservado'] != null) ReservedCard(amount: gps['reservado'] as String),
            const _Bubble(
              arrowUp: true,
              text: 'Reservado es lo que apartaste en tus bolsillos: no cuenta como dinero libre.',
            ),
            const SizedBox(height: 16),
            const _Bubble(
              arrowDown: true,
              text:
                  'Con + agregas a mano un gasto en efectivo. Si ese efectivo salió de un retiro, ya lo '
                  'contamos ahí y no vuelve a descontarse.',
            ),
            const Align(
              alignment: Alignment.centerRight,
              child: ExcludeSemantics(
                child: CircleAvatar(
                  radius: 30,
                  backgroundColor: Fsf.primario,
                  child: Icon(Icons.add, color: Fsf.sobrePrimario),
                ),
              ),
            ),
            const SizedBox(height: 24),
            FilledButton(onPressed: onDone, child: const Text('Entendido')),
          ],
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.text, this.arrowUp = false, this.arrowDown = false, this.arrowRight = false});

  final String text;
  final bool arrowUp, arrowDown;

  /// La flecha de arriba, a la derecha (señala la cabecera).
  final bool arrowRight;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (arrowUp)
        Align(
          alignment: arrowRight ? Alignment.centerRight : Alignment.centerLeft,
          child: Padding(
            padding: arrowRight ? const EdgeInsets.only(right: 96, top: 8) : const EdgeInsets.only(left: 40, top: 8),
            child: const CustomPaint(size: Size(24, 14), painter: _Arrow()),
          ),
        ),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: const BoxDecoration(color: Fsf.globo, borderRadius: BorderRadius.all(Radius.circular(24))),
        child: Text(text, style: const TextStyle(color: Fsf.sobrePrimario, fontSize: 16, height: 1.5)),
      ),
      if (arrowDown)
        const Align(
          alignment: Alignment.centerRight,
          child: Padding(
            padding: EdgeInsets.only(right: 18, bottom: 4),
            child: RotatedBox(
              quarterTurns: 2,
              child: CustomPaint(size: Size(24, 14), painter: _Arrow()),
            ),
          ),
        ),
    ],
  );
}

class _Arrow extends CustomPainter {
  const _Arrow();

  @override
  void paint(Canvas canvas, Size size) {
    final path = Path()
      ..moveTo(0, size.height)
      ..lineTo(size.width / 2, 0)
      ..lineTo(size.width, size.height)
      ..close();
    canvas.drawPath(path, Paint()..color = Fsf.globo);
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}
