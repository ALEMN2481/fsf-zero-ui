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
    await tester.pump(meTimeout); // deja vencer también la espera de /me
  });

  group('/me', () {
    MockClient slowMe(Duration delay) => MockClient((r) async {
      if (r.url.path == '/me') await Future<void>.delayed(delay);
      return http.Response('{"status":"ok"}', 200);
    });

    testWidgets('espera hasta 10 s la primera respuesta', (tester) async {
      await tester.pumpWidget(home(slowMe(const Duration(seconds: 7))));
      await tester.pump(const Duration(seconds: 6));
      expect(find.text('Verificando sesión…'), findsOneWidget);
      await tester.pump(const Duration(seconds: 2));
      expect(find.text('Sesión verificada'), findsOneWidget);
    });

    testWidgets('pasados 10 s sin respuesta muestra no verificada', (tester) async {
      await tester.pumpWidget(home(slowMe(const Duration(minutes: 1))));
      await tester.pump(meTimeout + const Duration(seconds: 1));
      expect(find.text('Sesión no verificada'), findsOneWidget);
      await tester.pump(const Duration(minutes: 1)); // deja terminar el temporizador del mock
    });
  });

  group('Gmail', () {
    Widget withMe(String meJson, {List<http.Request>? sent, List<Uri>? opened, Stream<Uri>? links}) => MaterialApp(
      home: HomeScreen(
        client: MockClient((r) async {
          sent?.add(r);
          if (r.url.path == '/me') return http.Response(meJson, 200);
          if (r.url.path == '/gmail/connect') {
            return http.Response('{"url":"https://accounts.google.com/o/oauth2/v2/auth?x=1"}', 200);
          }
          return http.Response('{"status":"ok"}', 200);
        }),
        token: 'jwt-usuario',
        links: links ?? const Stream.empty(),
        onSignOut: () {},
        openUrl: (url) async {
          opened?.add(url);
          return true;
        },
      ),
    );

    testWidgets('sin conexión ofrece conectar Gmail y abre Google con el token del usuario', (tester) async {
      final sent = <http.Request>[], opened = <Uri>[];
      await tester.pumpWidget(withMe('{"id":"u","gmail_status":null}', sent: sent, opened: opened));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Conectar Gmail'));
      await tester.pumpAndSettle();
      final connect = sent.singleWhere((r) => r.url.path == '/gmail/connect');
      expect(connect.method, 'POST');
      expect(connect.headers['Authorization'], 'Bearer jwt-usuario');
      expect(opened.single.host, 'accounts.google.com');
    });

    testWidgets('conectado no muestra el botón', (tester) async {
      await tester.pumpWidget(withMe('{"id":"u","gmail_status":"active"}'));
      await tester.pumpAndSettle();
      expect(find.text('Gmail conectado'), findsOneWidget);
      expect(find.text('Conectar Gmail'), findsNothing);
    });

    testWidgets('conexión caída pide reconectar', (tester) async {
      await tester.pumpWidget(withMe('{"id":"u","gmail_status":"needs_reconnect"}'));
      await tester.pumpAndSettle();
      expect(find.text('La conexión con Gmail se cayó'), findsOneWidget);
      expect(find.text('Reconectar Gmail'), findsOneWidget);
    });

    testWidgets('al volver a la app se refresca el estado', (tester) async {
      final sent = <http.Request>[];
      await tester.pumpWidget(withMe('{"id":"u","gmail_status":null}', sent: sent));
      await tester.pumpAndSettle();
      tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
      await tester.pumpAndSettle();
      expect(sent.where((r) => r.url.path == '/me').length, 2);
    });

    testWidgets('si la vuelta llega con error, lo dice y refresca', (tester) async {
      final links = StreamController<Uri>();
      final sent = <http.Request>[];
      await tester.pumpWidget(withMe('{"id":"u","gmail_status":null}', sent: sent, links: links.stream));
      await tester.pumpAndSettle();
      links.add(Uri.parse('co.finanzassinfiltro.fsfapp://gmail-connected?status=error'));
      await tester.pumpAndSettle();
      expect(find.text('No se pudo conectar Gmail, inténtalo de nuevo'), findsOneWidget);
      expect(sent.where((r) => r.url.path == '/me').length, 2);
      await links.close();
    });

    testWidgets('si la vuelta llega bien, no muestra error', (tester) async {
      final links = StreamController<Uri>();
      await tester.pumpWidget(withMe('{"id":"u","gmail_status":"active"}', links: links.stream));
      await tester.pumpAndSettle();
      links.add(Uri.parse('co.finanzassinfiltro.fsfapp://gmail-connected?status=ok'));
      await tester.pumpAndSettle();
      expect(find.text('No se pudo conectar Gmail, inténtalo de nuevo'), findsNothing);
      expect(find.text('Gmail conectado'), findsOneWidget);
      await links.close();
    });
  });
}
