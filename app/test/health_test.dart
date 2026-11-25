import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/home_screen.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

Widget home(http.Client client) => MaterialApp(
  home: HomeScreen(client: client, token: 't', onSignOut: () {}),
);

void main() {
  testWidgets('muestra conectado cuando /health responde ok', (tester) async {
    final client = MockClient((_) async => http.Response('{"status":"ok"}', 200));
    await tester.pumpWidget(home(client));
    await tester.pumpAndSettle();
    expect(find.text('Backend conectado'), findsOneWidget);
  });

  testWidgets('muestra no disponible cuando el backend falla', (tester) async {
    final client = MockClient((_) async => throw http.ClientException('sin red'));
    await tester.pumpWidget(home(client));
    await tester.pumpAndSettle();
    expect(find.text('Backend no disponible'), findsOneWidget);
  });

  testWidgets('muestra no disponible si el backend no responde a tiempo', (tester) async {
    final client = MockClient((_) => Completer<http.Response>().future); // nunca responde
    await tester.pumpWidget(home(client));
    expect(find.text('Conectando…'), findsOneWidget);
    await tester.pump(healthTimeout + const Duration(seconds: 1));
    expect(find.text('Backend no disponible'), findsOneWidget);
  });
}
