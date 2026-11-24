import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

// 10.0.2.2 = localhost del PC visto desde el emulador Android. Otro destino: --dart-define=API_URL=...
const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

const healthTimeout = Duration(seconds: 5);

void main() => runApp(MainApp(client: http.Client()));

class MainApp extends StatelessWidget {
  const MainApp({super.key, required this.client});

  final http.Client client;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Finanzas Sin Filtro',
      home: Scaffold(
        body: Center(
          child: FutureBuilder<String>(
            future: _checkHealth(),
            builder: (context, snap) => Text(
              snap.data ?? (snap.hasError ? 'Backend no disponible' : 'Conectando…'),
              style: Theme.of(context).textTheme.headlineSmall,
            ),
          ),
        ),
      ),
    );
  }

  Future<String> _checkHealth() async {
    final res = await client.get(Uri.parse('$apiUrl/health')).timeout(healthTimeout);
    final status = jsonDecode(res.body)['status'];
    return res.statusCode == 200 && status == 'ok' ? 'Backend conectado' : 'Backend no disponible';
  }
}
