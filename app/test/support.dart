import 'dart:convert';

import 'package:flutter/widgets.dart' show Size;
import 'package:flutter_test/flutter_test.dart';
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

/// Un teléfono alto (393×1745 lógicos): la principal entera a la vista, con el gráfico de la
/// semana (Paso 15B) los movimientos ya no caben en los 800×600 por defecto.
void tall(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 4800);
  tester.view.devicePixelRatio = 2.75;
  addTearDown(tester.view.reset);
}
