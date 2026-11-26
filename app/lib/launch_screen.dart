import 'package:flutter/material.dart';

import 'auth_screen.dart' show AppLogo;
import 'theme.dart';

/// Arranque (diseño «Launch», D14): se ve mientras la app inicia la conexión con Supabase.
/// El logo oficial (negro sobre blanco) va en una placa blanca para verse sobre el fondo oscuro.
class LaunchScreen extends StatelessWidget {
  const LaunchScreen({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Fsf.arranqueFondo,
      body: SafeArea(
        // Con el texto grande la columna no cabe: se desplaza en vez de desbordar.
        child: LayoutBuilder(
          builder: (context, box) => SingleChildScrollView(
            padding: const EdgeInsets.all(Fsf.margen),
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: box.maxHeight - 2 * Fsf.margen,
                minWidth: box.maxWidth - 2 * Fsf.margen,
              ),
              child: IntrinsicHeight(child: _content()),
            ),
          ),
        ),
      ),
    );
  }

  Widget _content() => const Column(
    children: [
      Spacer(),
      ClipRRect(
        borderRadius: BorderRadius.all(Radius.circular(32)),
        child: ColoredBox(
          color: Colors.white,
          child: Padding(padding: EdgeInsets.all(8), child: AppLogo(size: 112)),
        ),
      ),
      SizedBox(height: 32),
      Text(
        'Finanzas Sin Filtro',
        textAlign: TextAlign.center,
        style: TextStyle(fontWeight: FontWeight.w700, fontSize: 30, color: Colors.white),
      ),
      SizedBox(height: 12),
      Text(
        'Tus finanzas al día, sin enredos.',
        textAlign: TextAlign.center,
        style: TextStyle(fontWeight: FontWeight.w500, fontSize: 16, height: 1.5, color: Fsf.arranqueTextoSecundario),
      ),
      Spacer(),
      SizedBox(
        width: 112,
        child: LinearProgressIndicator(
          minHeight: 3,
          color: Colors.white,
          backgroundColor: Fsf.arranquePista,
          borderRadius: BorderRadius.all(Radius.circular(2)),
        ),
      ),
      SizedBox(height: 24),
      Text('Iniciando conexión segura…', style: TextStyle(fontSize: 12, color: Fsf.arranqueTextoSecundario)),
      SizedBox(height: 16),
    ],
  );
}
