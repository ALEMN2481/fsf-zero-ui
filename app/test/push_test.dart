import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/data_sources_screen.dart';
import 'package:fsf_app/home_screen.dart';
import 'package:fsf_app/movements.dart';
import 'package:fsf_app/push.dart';
import 'package:http/http.dart' as http;

import 'design_test.dart' show accessible, phone, wrap;
import 'home_test.dart' show backend, movements, now;
import 'support.dart';

/// Paso 14 (D16): avisos push en la app. Firebase se simula.

class FakePush implements Push {
  FakePush({this.granted = false, this.grantOnRequest = true});

  bool granted, grantOnRequest;
  final refresh = StreamController<String>.broadcast();
  final messages = StreamController<Map<String, String>>.broadcast();
  int requests = 0, settingsOpened = 0, lockScreenOpened = 0, deleted = 0;

  @override
  Future<String?> token() async => 'tok-1';
  @override
  Stream<String> get tokenRefresh => refresh.stream;
  @override
  Stream<Map<String, String>> get foreground => messages.stream;
  @override
  Future<bool> enabled() async => granted;
  @override
  Future<bool> requestPermission() async {
    requests++;
    return granted = grantOnRequest;
  }

  @override
  Future<void> openSettings() async => settingsOpened++;
  @override
  Future<void> openLockScreenSettings() async => lockScreenOpened++;
  @override
  Future<void> deleteToken() async => deleted++;
}

FakeBackend pushBackend() {
  final b = backend();
  b.routes['POST /devices'] = (_) => http.Response('', 204);
  b.routes['DELETE /devices'] = (_) => http.Response('', 204);
  b.routes['GET /transactions/t2'] = (_) => movements[1];
  b.routes['GET /coach/messages'] = (_) => const [];
  return b;
}

Future<void> pumpHome(
  WidgetTester tester,
  FakeBackend b,
  FakePush push, {
  StreamController<Uri>? links,
  bool askPush = false,
  bool showTutorial = false,
  VoidCallback? onPushAsked,
  VoidCallback? onSignOut,
}) async {
  await tester.pumpWidget(
    wrap(
      HomeScreen(
        client: b.client,
        token: 't',
        onSignOut: onSignOut ?? () {},
        links: links?.stream ?? const Stream.empty(),
        now: () => now,
        push: push,
        askPush: askPush,
        showTutorial: showTutorial,
        onPushAsked: onPushAsked,
      ),
    ),
  );
  await tester.pumpAndSettle();
}

void main() {
  testWidgets('registra el dispositivo al abrir y cuando FCM cambia el token', (tester) async {
    final b = pushBackend(), push = FakePush();
    await pumpHome(tester, b, push);
    expect(b.body('POST /devices'), {'token': 'tok-1'});
    push.refresh.add('tok-2');
    await tester.pumpAndSettle();
    expect(b.body('POST /devices'), {'token': 'tok-2'});
  });

  testWidgets('con la app abierta, un aviso refresca las cifras y lo dice brevemente', (tester) async {
    final b = pushBackend(), push = FakePush();
    await pumpHome(tester, b, push);
    final before = b.count('GET /gps');
    push.messages.add({'tipo': 'gasto_registrado', 'title': 'Nuevo gasto registrado'});
    await tester.pumpAndSettle();
    expect(b.count('GET /gps'), before + 1);
    expect(find.text('Nuevo gasto registrado'), findsOneWidget);
  });

  testWidgets('con la app abierta, tocar el mensaje del aviso abre la hoja del movimiento', (tester) async {
    final b = pushBackend(), push = FakePush();
    await pumpHome(tester, b, push);
    push.messages.add({'tipo': 'gasto_registrado', 'title': 'Nuevo gasto registrado', 'transaction_id': 't2'});
    await tester.pumpAndSettle();
    final bar = tester.widget<SnackBar>(find.byType(SnackBar));
    expect(bar.action?.label, 'Ver'); // también con lector de pantalla
    await tester.tap(find.text('Nuevo gasto registrado'));
    await tester.pumpAndSettle();
    expect(b.count('GET /transactions/t2'), 1);
    expect(find.byType(MovementSheet), findsOneWidget);
  });

  group('categoría que no se sabe', () {
    List<Map<String, dynamic>> asking() => [
      for (final m in movements) {...m, 'preguntar_categoria': m['id'] == 't3'},
    ];

    testWidgets('al abrir la app, la hoja de categorías aparece sola y una vez por sesión', (tester) async {
      final b = pushBackend();
      b.routes['GET /movements'] = (_) => asking();
      await pumpHome(tester, b, FakePush());
      expect(find.byType(MovementSheet), findsOneWidget);
      expect(find.text('¿A qué categoría pertenece este gasto?'), findsOneWidget);
      expect(find.textContaining('RESTAURANTE EJEMPLO SAS'), findsWidgets);
      Navigator.of(tester.element(find.byType(MovementSheet))).pop();
      await tester.pumpAndSettle();
      await tester.drag(find.byType(ListView).first, const Offset(0, 400)); // refrescar
      await tester.pumpAndSettle();
      expect(find.byType(MovementSheet), findsNothing);
    });

    testWidgets('al elegir, se guarda la categoría (y con ella la regla del comercio)', (tester) async {
      final b = pushBackend();
      b.routes['GET /movements'] = (_) => asking();
      b.routes['PATCH /transactions/t3/category'] = (_) => {'id': 't3'};
      await pumpHome(tester, b, FakePush());
      await tester.tap(find.text('Transporte'));
      await tester.pumpAndSettle();
      expect(b.body('PATCH /transactions/t3/category'), {'category_id': 'c-tra'});
    });

    testWidgets('no interrumpe el tutorial', (tester) async {
      final b = pushBackend();
      b.routes['GET /movements'] = (_) => asking();
      await pumpHome(tester, b, FakePush(), showTutorial: true);
      expect(find.byType(MovementSheet), findsNothing);
    });

    testWidgets('con la app abierta, el aviso de categoría abre la hoja sin tocar nada', (tester) async {
      final b = pushBackend(), push = FakePush();
      b.routes['GET /transactions/t3'] = (_) => movements[2];
      await pumpHome(tester, b, push);
      push.messages.add({'tipo': 'categorizar', 'title': '¿En qué categoría va este gasto?', 'transaction_id': 't3'});
      await tester.pumpAndSettle();
      expect(find.byType(MovementSheet), findsOneWidget);
      expect(find.byType(SnackBar), findsNothing);
    });
  });

  testWidgets('tocar el aviso abre la hoja del movimiento; el de Gmail, Fuentes de Datos', (tester) async {
    final b = pushBackend(), links = StreamController<Uri>();
    await pumpHome(tester, b, FakePush(), links: links);
    links.add(Uri.parse('co.finanzassinfiltro.fsfapp://movimiento/t2'));
    await tester.pumpAndSettle();
    expect(b.count('GET /transactions/t2'), 1);
    expect(find.byType(MovementSheet), findsOneWidget);
    Navigator.of(tester.element(find.byType(MovementSheet))).pop();
    await tester.pumpAndSettle();
    links.add(Uri.parse('co.finanzassinfiltro.fsfapp://fuentes'));
    await tester.pumpAndSettle();
    expect(find.byType(DataSourcesScreen), findsOneWidget);
  });

  testWidgets('el permiso se explica y se pide una vez, tras el tutorial', (tester) async {
    phone(tester);
    final b = pushBackend(), push = FakePush();
    var asked = 0;
    // Con el tutorial en pantalla no se pregunta.
    await pumpHome(tester, b, push, askPush: true, showTutorial: true, onPushAsked: () => asked++);
    expect(find.byType(PushPrompt), findsNothing);
    // Al cerrarlo, sí.
    await pumpHome(tester, b, push, askPush: true, onPushAsked: () => asked++);
    expect(find.byType(PushPrompt), findsOneWidget);
    expect(find.textContaining('puedes ocultarlas'), findsOneWidget);
    await tester.tap(find.text('Activar avisos'));
    await tester.pumpAndSettle();
    expect((push.requests, asked), (1, 1));
  });

  testWidgets('«Ahora no» no pide el permiso; si ya estaba activo, no pregunta', (tester) async {
    final b = pushBackend(), push = FakePush();
    var asked = 0;
    await pumpHome(tester, b, push, askPush: true, onPushAsked: () => asked++);
    await tester.tap(find.text('Ahora no'));
    await tester.pumpAndSettle();
    expect((push.requests, asked), (0, 1));

    final active = FakePush(granted: true);
    await tester.pumpWidget(const SizedBox()); // pantalla nueva (otro inicio de la app)
    await pumpHome(tester, pushBackend(), active, askPush: true, onPushAsked: () => asked++);
    expect(find.byType(PushPrompt), findsNothing);
    expect(asked, 2);
  });

  testWidgets('sin presupuesto no se pregunta todavía', (tester) async {
    final b = pushBackend();
    b.routes['GET /gps'] = (_) => {'estado': 'sin_presupuesto'};
    await pumpHome(tester, b, FakePush(), askPush: true);
    expect(find.byType(PushPrompt), findsNothing);
  });

  testWidgets('al cerrar sesión, el teléfono deja de recibir los avisos de la cuenta', (tester) async {
    final b = pushBackend(), push = FakePush();
    var out = 0;
    await pumpHome(tester, b, push, onSignOut: () => out++);
    await tester.tap(find.byTooltip('Ajustes'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cerrar sesión'));
    await tester.pumpAndSettle();
    expect(b.body('DELETE /devices'), {'token': 'tok-1'});
    expect((push.deleted, out), (1, 1));
  });

  testWidgets('con el token renovado, las llamadas usan el nuevo (no dan 401 a la hora)', (tester) async {
    final b = pushBackend();
    Widget home(String token) =>
        wrap(HomeScreen(client: b.client, token: token, onSignOut: () {}, links: const Stream.empty(), now: () => now));
    await tester.pumpWidget(home('viejo'));
    await tester.pumpAndSettle();
    await tester.pumpWidget(home('nuevo')); // Supabase renovó la sesión
    await tester.drag(find.byType(ListView).first, const Offset(0, 400)); // tirar para refrescar
    await tester.pumpAndSettle();
    expect(b.sent.last.headers['Authorization'], 'Bearer nuevo');
  });

  group('Fuentes de Datos: desconectar Gmail', () {
    Future<void> pump(WidgetTester tester, Future<bool> Function() disconnect) async {
      var status = 'active';
      await tester.pumpWidget(
        wrap(
          DataSourcesScreen(
            status: () async => status,
            connect: () async {},
            disconnect: () async {
              status = 'none';
              return disconnect();
            },
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('Desconectar Gmail'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Desconectar'));
      await tester.pumpAndSettle();
    }

    testWidgets('si Google no confirma la revocación, lo dice', (tester) async {
      await pump(tester, () async => false);
      expect(find.text(DataSourcesScreen.revokeUnconfirmed), findsOneWidget);
      expect(find.text('Conectar Gmail'), findsOneWidget); // la conexión se borró igual
    });

    testWidgets('confirmada: «Gmail desconectado»', (tester) async {
      await pump(tester, () async => true);
      expect(find.text('Gmail desconectado'), findsOneWidget);
      expect(find.text(DataSourcesScreen.revokeUnconfirmed), findsNothing);
    });

    testWidgets('la principal llama al backend y lee «revocada»', (tester) async {
      final b = pushBackend();
      b.routes['POST /gmail/disconnect'] = (_) => {'revocada': false};
      await pumpHome(tester, b, FakePush());
      await tester.tap(find.byTooltip('Ajustes'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Fuentes de datos'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Desconectar Gmail'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('Desconectar'));
      await tester.pumpAndSettle();
      expect(b.count('POST /gmail/disconnect'), 1);
      expect(find.text(DataSourcesScreen.revokeUnconfirmed), findsOneWidget);
    });
  });

  group('Fuentes de Datos: avisos', () {
    Future<void> pump(WidgetTester tester, FakePush push, {double scale = 1}) async {
      await tester.pumpWidget(
        wrap(
          DataSourcesScreen(status: () async => 'active', connect: () async {}, push: push),
          scale: scale,
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('desactivados: el botón pide el permiso y, si Android ya no pregunta, abre los ajustes', (
      tester,
    ) async {
      final push = FakePush(grantOnRequest: false);
      await pump(tester, push);
      expect(find.textContaining('Desactivados'), findsOneWidget);
      await tester.tap(find.text('Activar avisos'));
      await tester.pumpAndSettle();
      expect((push.requests, push.settingsOpened), (1, 1));
    });

    testWidgets('activados: lo dice y explica cómo ocultar las cifras en la pantalla de bloqueo', (tester) async {
      final push = FakePush(granted: true);
      await pump(tester, push);
      expect(find.textContaining('Activados'), findsOneWidget);
      expect(find.text('Activar avisos'), findsNothing);
      await tester.tap(find.text('Ocultar cifras en la pantalla de bloqueo'));
      await tester.pumpAndSettle();
      expect(push.lockScreenOpened, 1);
    });

    testWidgets('al 200 % no desborda y cumple las guías (Fuentes y la explicación)', (tester) async {
      phone(tester);
      await pump(tester, FakePush(), scale: 2);
      await accessible(tester);
      await pump(tester, FakePush(granted: true), scale: 2);
      await accessible(tester);
      await tester.pumpWidget(wrap(const Scaffold(body: PushPrompt()), scale: 2));
      await tester.pumpAndSettle();
      await accessible(tester);
    });
  });
}
