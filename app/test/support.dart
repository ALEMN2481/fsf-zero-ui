import 'dart:convert';

import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

/// Backend falso: respuestas por "MÉTODO /ruta"; guarda lo enviado.
class FakeBackend {
  FakeBackend(this.routes);
  final Map<String, Object? Function(http.Request)> routes;
  final sent = <http.Request>[];

  late final client = MockClient((r) async {
    sent.add(r);
    final handler = routes['${r.method} ${r.url.path}'];
    if (handler == null) return http.Response('{"detail":"no encontrado"}', 404);
    final out = handler(r);
    if (out is http.Response) return out;
    return http.Response.bytes(utf8.encode(jsonEncode(out)), 200);
  });

  int count(String route) => sent.where((r) => '${r.method} ${r.url.path}' == route).length;
  Map<String, dynamic> body(String route) =>
      jsonDecode(sent.lastWhere((r) => '${r.method} ${r.url.path}' == route).body) as Map<String, dynamic>;
}
