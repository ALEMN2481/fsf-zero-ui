import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/auth_screen.dart';
import 'package:fsf_app/main.dart';
import 'package:fsf_app/session_storage.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:local_auth/local_auth.dart';
import 'package:local_auth_android/local_auth_android.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

final user = {
  'id': 'user-a',
  'aud': 'authenticated',
  'email': 'a@test.co',
  'created_at': '2026-11-24T00:00:00Z',
  'app_metadata': {},
  'user_metadata': {},
};

Map<String, dynamic> sessionJson() => {
  'access_token': 'token-a',
  'token_type': 'bearer',
  'expires_in': 3600,
  'expires_at': DateTime.now().add(const Duration(hours: 1)).millisecondsSinceEpoch ~/ 1000,
  'refresh_token': 'refresh-a',
  'user': user,
};

/// Biometría falsa: [supported] = el dispositivo tiene biometría o PIN; [answers] = resultados de authenticate.
class FakeLock extends Fake implements LocalAuthentication {
  FakeLock({this.supported = true, List<bool>? answers}) : answers = answers ?? [true];
  bool supported;
  final List<bool> answers;
  int prompts = 0;
  Iterable<Object> messages = const [];

  @override
  Future<bool> isDeviceSupported() async => supported;

  @override
  Future<bool> authenticate({
    required String localizedReason,
    Iterable<Object> authMessages = const [],
    bool biometricOnly = false,
    bool sensitiveTransaction = true,
    bool persistAcrossBackgrounding = false,
  }) async {
    messages = authMessages;
    final answer = answers[prompts.clamp(0, answers.length - 1)];
    prompts++;
    return answer;
  }
}

class Harness {
  Harness({Map<String, String>? stored}) {
    FlutterSecureStorage.setMockInitialValues(stored ?? {});
  }

  final requests = <http.Request>[];
  http.Response Function(http.Request) supabase = (_) => http.Response('{}', 200);
  var clock = DateTime(2026, 11, 24, 12);
  final storage = const FlutterSecureStorage();

  late final auth = GoTrueClient(
    url: 'http://supabase.test/auth/v1',
    httpClient: MockClient((r) async {
      requests.add(r);
      return supabase(r);
    }),
    autoRefreshToken: false,
    flowType: AuthFlowType.implicit,
  );

  final opened = <Uri>[];

  final backend = MockClient((r) async => http.Response('{"status":"ok"}', 200));

  Widget app(FakeLock lock) => FsfApp(
    auth: auth,
    sessionStore: SecureSessionStorage(storage),
    storage: storage,
    deviceLock: lock,
    client: backend,
    now: () => clock,
    openUrl: (url) async {
      opened.add(url);
      return true;
    },
  );

  Future<void> restoreSession() => auth.setInitialSession(jsonEncode(sessionJson()));
}

/// La pantalla principal está a la vista (su menú «Más opciones»).
final homeShown = find.byTooltip('Más opciones');

Future<void> fill(WidgetTester tester, String email, String password) async {
  await tester.enterText(find.widgetWithText(TextFormField, 'Correo'), email);
  await tester.enterText(find.widgetWithText(TextFormField, 'Contraseña'), password);
}

void main() {
  group('formulario de acceso', () {
    testWidgets('tiene 2 campos como máximo (RQN 05)', (tester) async {
      await tester.pumpWidget(Harness().app(FakeLock()));
      expect(find.byType(TextFormField), findsNWidgets(2));
      await tester.tap(find.text('¿No tienes cuenta? Crear una'));
      await tester.pump();
      expect(find.byType(TextFormField), findsNWidgets(2));
    });

    testWidgets('no envía nada con un correo inválido o una contraseña corta', (tester) async {
      final h = Harness();
      await tester.pumpWidget(h.app(FakeLock()));
      await fill(tester, 'no-es-correo', 'corta12');
      await tester.tap(find.text('Entrar'));
      await tester.pump();
      expect(find.text('Escribe un correo válido'), findsOneWidget);
      expect(find.text('Mínimo 8 caracteres'), findsOneWidget);
      expect(h.requests, isEmpty);
    });

    testWidgets('el registro pide confirmar el correo y redirige a la app', (tester) async {
      final h = Harness()..supabase = (_) => http.Response(jsonEncode(user), 200);
      await tester.pumpWidget(h.app(FakeLock()));
      await tester.tap(find.text('¿No tienes cuenta? Crear una'));
      await tester.pump();
      await fill(tester, 'a@test.co', 'clave-segura-1');
      await tester.tap(find.text('Crear cuenta'));
      await tester.pumpAndSettle();
      expect(find.text('Revisa tu correo para confirmar la cuenta'), findsOneWidget);
      expect(h.requests.single.url.path, '/auth/v1/signup');
      expect(h.requests.single.url.queryParameters['redirect_to'], authRedirect);
    });

    testWidgets('avisa si el correo no está confirmado', (tester) async {
      final h = Harness()
        ..supabase = (_) =>
            http.Response('{"code":400,"error_code":"email_not_confirmed","msg":"Email not confirmed"}', 400);
      await tester.pumpWidget(h.app(FakeLock()));
      await fill(tester, 'a@test.co', 'clave-segura-1');
      await tester.tap(find.text('Entrar'));
      await tester.pumpAndSettle();
      expect(find.text('Confirma tu correo antes de iniciar sesión'), findsOneWidget);
    });

    testWidgets('con credenciales correctas entra sin pedir biometría', (tester) async {
      final h = Harness()..supabase = (_) => http.Response(jsonEncode(sessionJson()), 200);
      final lock = FakeLock();
      await tester.pumpWidget(h.app(lock));
      await fill(tester, 'a@test.co', 'clave-segura-1');
      await tester.tap(find.text('Entrar'));
      await tester.pumpAndSettle();
      expect(homeShown, findsOneWidget);
      expect(lock.prompts, 0);
    });
  });

  testWidgets('Continuar con Google abre Google con el enlace de vuelta a la app', (tester) async {
    final h = Harness();
    await tester.pumpWidget(h.app(FakeLock()));
    await tester.tap(find.text('Continuar con Google'));
    await tester.pumpAndSettle();
    final url = h.opened.single;
    expect(url.path, '/auth/v1/authorize');
    expect(url.queryParameters['provider'], 'google');
    expect(url.queryParameters['redirect_to'], authRedirect);
    expect(find.byType(TextFormField), findsNWidgets(2)); // el botón no añade campos
  });

  group('bloqueo local', () {
    testWidgets('al abrir con sesión guardada pide desbloqueo; si falla, sigue bloqueada', (tester) async {
      final h = Harness();
      await h.restoreSession();
      final lock = FakeLock(answers: [false, true]);
      await tester.pumpWidget(h.app(lock));
      await tester.pumpAndSettle();
      expect(find.text('Desbloquear'), findsOneWidget);
      expect(homeShown, findsNothing);

      await tester.tap(find.text('Desbloquear'));
      await tester.pumpAndSettle();
      expect(homeShown, findsOneWidget);
      expect(lock.prompts, 2);
      final android = lock.messages.whereType<AndroidAuthMessages>().single;
      expect(android.cancelButton, 'Cancelar'); // diálogo del sistema en español
    });

    testWidgets('vuelve a bloquear tras 5 minutos o más en segundo plano, no antes', (tester) async {
      final h = Harness();
      await h.restoreSession();
      final lock = FakeLock(answers: [true, false]);
      await tester.pumpWidget(h.app(lock));
      await tester.pumpAndSettle();
      expect(lock.prompts, 1);

      Future<void> background(Duration d) async {
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.paused);
        h.clock = h.clock.add(d);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.hidden);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.inactive);
        tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
        await tester.pumpAndSettle();
      }

      await background(const Duration(minutes: 4, seconds: 59));
      expect(lock.prompts, 1);
      expect(homeShown, findsOneWidget);

      await background(const Duration(minutes: 5));
      expect(lock.prompts, 2);
      expect(find.text('Desbloquear'), findsOneWidget);
    });

    testWidgets('sin biometría ni PIN no bloquea y avisa una sola vez', (tester) async {
      final h = Harness();
      await h.restoreSession();
      await tester.pumpWidget(h.app(FakeLock(supported: false)));
      await tester.pumpAndSettle();
      expect(homeShown, findsOneWidget);
      expect(find.text(lockWarning), findsOneWidget);
      expect(await h.storage.read(key: 'lock_warning_shown'), isNotNull);

      // Segunda apertura de la app: ya no se repite el aviso.
      await tester.pumpWidget(const SizedBox());
      await tester.pumpWidget(h.app(FakeLock(supported: false)));
      await tester.pumpAndSettle();
      expect(find.text(lockWarning), findsNothing);
    });
  });

  testWidgets('cerrar sesión borra la sesión del almacenamiento seguro', (tester) async {
    final h = Harness(stored: {supabasePersistSessionKey: jsonEncode(sessionJson())})
      ..supabase = (_) => http.Response('', 204);
    await h.restoreSession();
    await tester.pumpWidget(h.app(FakeLock()));
    await tester.pumpAndSettle();
    expect(await h.storage.read(key: supabasePersistSessionKey), isNotNull);

    await tester.tap(find.byTooltip('Más opciones'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Cerrar sesión'));
    await tester.pumpAndSettle();
    expect(await h.storage.read(key: supabasePersistSessionKey), isNull);
    expect(find.text('Entrar'), findsOneWidget);
  });

  testWidgets('fuera de primer plano una capa tapa la app (pantalla de recientes)', (tester) async {
    final h = Harness(stored: {supabasePersistSessionKey: jsonEncode(sessionJson())});
    await h.restoreSession();
    await tester.pumpWidget(h.app(FakeLock(supported: false)));
    await tester.pumpAndSettle();
    expect(homeShown, findsOneWidget);
    expect(find.byType(PrivacyCover), findsNothing);
    for (final state in [AppLifecycleState.inactive, AppLifecycleState.hidden, AppLifecycleState.paused]) {
      tester.binding.handleAppLifecycleStateChanged(state);
      await tester.pump();
      expect(find.byType(PrivacyCover), findsOneWidget, reason: '$state');
      // Con estilo del tema, no el de emergencia (rojo y subrayado) que sale sin Material.
      final style = DefaultTextStyle.of(tester.element(find.text('Finanzas Sin Filtro'))).style;
      expect(style.decoration, isNot(TextDecoration.underline));
      expect(style.color, isNot(const Color(0xd0ff0000)));
    }
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pump();
    expect(find.byType(PrivacyCover), findsNothing);
  });
}
