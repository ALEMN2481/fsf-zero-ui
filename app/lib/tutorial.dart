import 'package:flutter/material.dart';

import 'home_screen.dart' show ReservedCard;
import 'money.dart';
import 'theme.dart';

/// «Primer vistazo» (D14): se muestra una vez sobre la principal. Usa las cifras reales del
/// backend; sin «Obligaciones» (el motor no las calcula) ni el Coach (Paso 13).
class TutorialOverlay extends StatelessWidget {
  const TutorialOverlay({super.key, required this.gps, required this.onDone});

  final Map<String, dynamic> gps;
  final VoidCallback onDone;

  @override
  Widget build(BuildContext context) {
    final today = gps['disponible_hoy'] as String;
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
            const SizedBox(height: 32),
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
            const SizedBox(height: 16),
            if (gps['reservado'] != null) ReservedCard(amount: gps['reservado'] as String),
            const _Bubble(
              arrowUp: true,
              text: 'Reservado es lo que apartaste en tus bolsillos: no cuenta como dinero libre.',
            ),
            const SizedBox(height: 32),
            FilledButton(onPressed: onDone, child: const Text('Entendido')),
          ],
        ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.text, this.arrowUp = false});

  final String text;
  final bool arrowUp;

  @override
  Widget build(BuildContext context) => Column(
    crossAxisAlignment: CrossAxisAlignment.start,
    children: [
      if (arrowUp)
        const Padding(
          padding: EdgeInsets.only(left: 40, top: 8),
          child: CustomPaint(size: Size(24, 14), painter: _Arrow()),
        ),
      Container(
        width: double.infinity,
        padding: const EdgeInsets.all(20),
        decoration: const BoxDecoration(color: Fsf.globo, borderRadius: BorderRadius.all(Radius.circular(24))),
        child: Text(text, style: const TextStyle(color: Fsf.sobrePrimario, fontSize: 16, height: 1.5)),
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
