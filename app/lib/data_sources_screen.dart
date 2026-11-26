import 'package:flutter/material.dart';

import 'theme.dart';

/// Fuentes de Datos (ajustes, D7 y D14): solo la conexión de Gmail y su estado. Sin reenvío de
/// correos ni conexión bancaria (fuera de alcance).
class DataSourcesScreen extends StatefulWidget {
  const DataSourcesScreen({super.key, required this.status, required this.connect});

  /// Estado de Gmail de /me: null (sin conectar), 'active' o 'needs_reconnect'.
  final Future<String?> Function() status;
  final Future<void> Function() connect;

  @override
  State<DataSourcesScreen> createState() => _DataSourcesScreenState();
}

class _DataSourcesScreenState extends State<DataSourcesScreen> with WidgetsBindingObserver {
  late Future<String?> _status = widget.status();

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    // Al volver de Google se ve el estado nuevo.
    if (state == AppLifecycleState.resumed) {
      setState(() {
        _status = widget.status();
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Fuentes de Datos')),
      body: ListView(
        padding: const EdgeInsets.all(Fsf.margen),
        children: [
          const Text(
            'Automatiza tus finanzas',
            style: TextStyle(fontWeight: FontWeight.w700, fontSize: 32, height: 1.15),
          ),
          const SizedBox(height: 12),
          const Text(
            'Conecta tu correo y leeremos las alertas de tu banco y tus facturas electrónicas, '
            'sin que tengas que digitar nada.',
            style: TextStyle(fontSize: 16, height: 1.5, color: Fsf.textoSecundario),
          ),
          const SizedBox(height: 32),
          FutureBuilder<String?>(
            future: _status,
            builder: (context, snap) => _GmailCard(
              loading: snap.connectionState != ConnectionState.done,
              failed: snap.hasError,
              status: snap.data,
              onConnect: () async {
                await widget.connect();
                if (mounted) {
                  setState(() {
                    _status = widget.status();
                  });
                }
              },
            ),
          ),
          const SizedBox(height: 48),
          const Icon(Icons.lock_outline, color: Fsf.textoSecundario),
          const SizedBox(height: 8),
          const Text(
            'Tus datos viajan y se guardan cifrados. Solo guardamos los correos de tu banco y de '
            'facturación electrónica, y puedes desconectar Gmail cuando quieras.',
            textAlign: TextAlign.center,
            style: Fsf.ayuda,
          ),
        ],
      ),
    );
  }
}

class _GmailCard extends StatelessWidget {
  const _GmailCard({required this.loading, required this.failed, required this.status, required this.onConnect});

  final bool loading, failed;
  final String? status;
  final VoidCallback onConnect;

  @override
  Widget build(BuildContext context) {
    final (String detail, String? action) = switch (status) {
      _ when loading => ('Comprobando…', null),
      _ when failed => ('No pudimos comprobar la conexión', null),
      'active' => ('Conectado. Leemos tus alertas y facturas automáticamente.', null),
      'needs_reconnect' => ('La conexión con Gmail se cayó. Vuelve a conectarla.', 'Reconectar Gmail'),
      _ => ('Sin conectar.', 'Conectar Gmail'),
    };
    return Container(
      padding: const EdgeInsets.all(Fsf.margen),
      decoration: const BoxDecoration(color: Fsf.superficie, borderRadius: BorderRadius.all(Radius.circular(20))),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              const Icon(Icons.mail_outline),
              const SizedBox(width: 12),
              const Expanded(child: Text('Gmail', style: Fsf.tarjeta)),
              if (status == 'active') const Icon(Icons.check_circle, semanticLabel: 'Conectado'),
            ],
          ),
          const SizedBox(height: 12),
          Text(
            detail,
            key: const Key('gmail_estado'),
            style: const TextStyle(color: Fsf.textoSecundarioEnSuperficie),
          ),
          if (action != null) ...[const SizedBox(height: 16), FilledButton(onPressed: onConnect, child: Text(action))],
        ],
      ),
    );
  }
}
