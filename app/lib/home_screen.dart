import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

// 10.0.2.2 = localhost del PC visto desde el emulador Android. Otro destino: --dart-define=API_URL=...
const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

const healthTimeout = Duration(seconds: 5);

/// /me valida el token: la primera llamada puede tardar más (el backend descarga el JWKS).
const meTimeout = Duration(seconds: 10);

/// Pantalla principal provisional: estado del backend y sesión validada por /me.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, required this.client, required this.token, required this.onSignOut});

  final http.Client client;
  final String token;
  final VoidCallback onSignOut;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  late final Future<String> _health = _checkHealth();
  late final Future<String> _me = _checkMe();

  Future<String> _checkHealth() async {
    final res = await widget.client.get(Uri.parse('$apiUrl/health')).timeout(healthTimeout);
    final status = jsonDecode(res.body)['status'];
    return res.statusCode == 200 && status == 'ok' ? 'Backend conectado' : 'Backend no disponible';
  }

  Future<String> _checkMe() async {
    final res = await widget.client
        .get(Uri.parse('$apiUrl/me'), headers: {'Authorization': 'Bearer ${widget.token}'})
        .timeout(meTimeout);
    return res.statusCode == 200 ? 'Sesión verificada' : 'Sesión no verificada';
  }

  Widget _status(Future<String> future, String loading, String failure) => FutureBuilder<String>(
    future: future,
    builder: (context, snap) =>
        Text(snap.data ?? (snap.hasError ? failure : loading), style: Theme.of(context).textTheme.titleMedium),
  );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            _status(_health, 'Conectando…', 'Backend no disponible'),
            const SizedBox(height: 8),
            _status(_me, 'Verificando sesión…', 'Sesión no verificada'),
            const SizedBox(height: 24),
            TextButton(onPressed: widget.onSignOut, child: const Text('Cerrar sesión')),
          ],
        ),
      ),
    );
  }
}
