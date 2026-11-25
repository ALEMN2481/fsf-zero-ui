import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'auth_screen.dart' show openInBrowser;

// 10.0.2.2 = localhost del PC visto desde el emulador Android. Otro destino: --dart-define=API_URL=...
const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

const healthTimeout = Duration(seconds: 5);

/// /me valida el token: la primera llamada puede tardar más (el backend descarga el JWKS).
const meTimeout = Duration(seconds: 10);

/// Pantalla principal provisional: estado del backend, sesión validada por /me y conexión con Gmail.
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.client,
    required this.token,
    required this.onSignOut,
    this.openUrl = openInBrowser,
  });

  final http.Client client;
  final String token;
  final VoidCallback onSignOut;
  final Future<bool> Function(Uri url) openUrl;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  late final Future<String> _health = _checkHealth();
  late Future<Map<String, dynamic>?> _me = _loadMe();
  bool _connecting = false;

  Map<String, String> get _auth => {'Authorization': 'Bearer ${widget.token}'};

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
    // Al volver de Google (enlace gmail-connected) o del navegador, se refresca el estado de Gmail.
    if (state == AppLifecycleState.resumed) {
      setState(() {
        _me = _loadMe();
      });
    }
  }

  Future<String> _checkHealth() async {
    final res = await widget.client.get(Uri.parse('$apiUrl/health')).timeout(healthTimeout);
    final status = jsonDecode(res.body)['status'];
    return res.statusCode == 200 && status == 'ok' ? 'Backend conectado' : 'Backend no disponible';
  }

  /// Perfil de /me (con `gmail_status`) o null si la sesión no se pudo verificar.
  Future<Map<String, dynamic>?> _loadMe() async {
    final res = await widget.client.get(Uri.parse('$apiUrl/me'), headers: _auth).timeout(meTimeout);
    return res.statusCode == 200 ? jsonDecode(res.body) as Map<String, dynamic> : null;
  }

  Future<void> _connectGmail() async {
    setState(() => _connecting = true);
    String? error;
    try {
      final res = await widget.client.post(Uri.parse('$apiUrl/gmail/connect'), headers: _auth).timeout(meTimeout);
      if (res.statusCode != 200 || !await widget.openUrl(Uri.parse(jsonDecode(res.body)['url'] as String))) {
        error = 'No se pudo iniciar la conexión con Gmail';
      }
    } catch (_) {
      error = 'No se pudo iniciar la conexión con Gmail';
    }
    if (!mounted) return;
    setState(() => _connecting = false);
    if (error != null) ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(error)));
  }

  Widget _gmail(Map<String, dynamic> me) {
    final status = me['gmail_status'];
    if (status == 'active') return const Text('Gmail conectado');
    return Column(
      children: [
        if (status == 'needs_reconnect') const Text('La conexión con Gmail se cayó'),
        FilledButton(
          onPressed: _connecting ? null : _connectGmail,
          child: Text(status == 'needs_reconnect' ? 'Reconectar Gmail' : 'Conectar Gmail'),
        ),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final style = Theme.of(context).textTheme.titleMedium;
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            FutureBuilder<String>(
              future: _health,
              builder: (context, snap) =>
                  Text(snap.data ?? (snap.hasError ? 'Backend no disponible' : 'Conectando…'), style: style),
            ),
            const SizedBox(height: 8),
            FutureBuilder<Map<String, dynamic>?>(
              future: _me,
              builder: (context, snap) {
                if (snap.connectionState != ConnectionState.done) return Text('Verificando sesión…', style: style);
                final me = snap.data;
                if (me == null) return Text('Sesión no verificada', style: style);
                return Column(
                  children: [
                    Text('Sesión verificada', style: style),
                    const SizedBox(height: 16),
                    _gmail(me),
                  ],
                );
              },
            ),
            const SizedBox(height: 24),
            TextButton(onPressed: widget.onSignOut, child: const Text('Cerrar sesión')),
          ],
        ),
      ),
    );
  }
}
