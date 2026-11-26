import 'package:flutter/material.dart';

import 'push.dart';
import 'theme.dart';

/// Fuentes de Datos (ajustes, D7 y D14): solo la conexión de Gmail y su estado. Sin reenvío de
/// correos ni conexión bancaria (fuera de alcance).
class DataSourcesScreen extends StatefulWidget {
  const DataSourcesScreen({super.key, required this.status, required this.connect, this.push});

  /// Estado de Gmail de /me: null (sin conectar), 'active' o 'needs_reconnect'.
  final Future<String?> Function() status;
  final Future<void> Function() connect;

  /// Avisos push (Paso 14): estado del permiso y cómo activarlo. Sin [push], no se muestra.
  final Push? push;

  @override
  State<DataSourcesScreen> createState() => _DataSourcesScreenState();
}

class _DataSourcesScreenState extends State<DataSourcesScreen> with WidgetsBindingObserver {
  late Future<String?> _status = widget.status();
  late Future<bool>? _push = widget.push?.enabled();

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
        _push = widget.push?.enabled();
      });
    }
  }

  /// Si Android ya no muestra el diálogo (permiso negado antes), se abren los ajustes de la app.
  Future<void> _enablePush() async {
    final push = widget.push!;
    if (!await push.requestPermission()) await push.openSettings();
    if (mounted) {
      setState(() {
        _push = push.enabled();
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
          if (_push != null) ...[
            const SizedBox(height: 16),
            FutureBuilder<bool>(
              future: _push,
              builder: (context, snap) => _PushCard(
                enabled: snap.data,
                onEnable: _enablePush,
                onLockScreen: widget.push!.openLockScreenSettings,
              ),
            ),
          ],
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

class _PushCard extends StatelessWidget {
  const _PushCard({required this.enabled, required this.onEnable, required this.onLockScreen});

  final bool? enabled; // null: comprobando
  final VoidCallback onEnable, onLockScreen;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(Fsf.margen),
    decoration: const BoxDecoration(color: Fsf.superficie, borderRadius: BorderRadius.all(Radius.circular(20))),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Row(
          children: [
            const Icon(Icons.notifications_none),
            const SizedBox(width: 12),
            const Expanded(child: Text('Avisos', style: Fsf.tarjeta)),
            if (enabled == true) const Icon(Icons.check_circle, semanticLabel: 'Activados'),
          ],
        ),
        const SizedBox(height: 12),
        Text(
          switch (enabled) {
            null => 'Comprobando…',
            // D16: Android muestra el contenido en la pantalla de bloqueo salvo que el usuario oculte
            // el contenido sensible; la app no puede imponerlo.
            true =>
              'Activados. Te avisamos de tus gastos con el monto y lo que puedes gastar hoy. '
                  'Si no quieres que esas cifras se vean con el teléfono bloqueado, oculta el '
                  'contenido sensible en los ajustes de notificaciones.',
            false => 'Desactivados. Actívalos para saber cuándo registramos un gasto.',
          },
          key: const Key('avisos_estado'),
          style: const TextStyle(color: Fsf.textoSecundarioEnSuperficie),
        ),
        if (enabled == false) ...[
          const SizedBox(height: 16),
          FilledButton(onPressed: onEnable, child: const Text('Activar avisos')),
        ],
        if (enabled == true) ...[
          const SizedBox(height: 16),
          OutlinedButton(onPressed: onLockScreen, child: const Text('Ocultar cifras en la pantalla de bloqueo')),
        ],
      ],
    ),
  );
}
