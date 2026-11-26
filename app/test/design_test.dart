import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/auth_screen.dart';
import 'package:fsf_app/data_sources_screen.dart';
import 'package:fsf_app/home_screen.dart';
import 'package:fsf_app/launch_screen.dart';
import 'package:fsf_app/theme.dart';
import 'package:fsf_app/tutorial.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'home_test.dart' show backend, gps, now;

/// Paso 12B (D14): pantallas nuevas del diseño, accesibilidad y textos honestos.

Widget wrap(Widget child, {double scale = 1}) => MaterialApp(
  theme: fsfTheme(),
  home: MediaQuery(
    data: MediaQueryData(size: const Size(393, 851), textScaler: TextScaler.linear(scale)),
    child: child,
  ),
);

void phone(WidgetTester tester) {
  tester.view.physicalSize = const Size(1080, 2340);
  tester.view.devicePixelRatio = 2.75;
  addTearDown(tester.view.reset);
}

Future<void> accessible(WidgetTester tester) async {
  expect(tester.takeException(), isNull); // sin desbordes
  await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
  await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
  await expectLater(tester, meetsGuideline(textContrastGuideline));
}

void main() {
  group('tutorial «Primer vistazo»', () {
    testWidgets('se muestra con las cifras reales, sin Obligaciones ni Coach, y se cierra', (tester) async {
      phone(tester);
      var done = 0;
      await tester.pumpWidget(
        wrap(
          HomeScreen(
            client: backend().client,
            token: 't',
            onSignOut: () {},
            links: const Stream.empty(),
            now: () => now,
            showTutorial: true,
            onTutorialDone: () => done++,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(TutorialOverlay), findsOneWidget);
      expect(find.textContaining('Reservado es lo que apartaste'), findsOneWidget);
      for (final banned in ['Obligaciones', 'Coach', 'obligaciones']) {
        expect(find.textContaining(banned), findsNothing, reason: banned);
      }
      await tester.tap(find.text('Entendido'));
      expect(done, 1);
    });

    testWidgets('no se muestra mientras no hay presupuesto', (tester) async {
      await tester.pumpWidget(
        wrap(
          HomeScreen(
            client: backend(state: {'estado': 'sin_presupuesto'}).client,
            token: 't',
            onSignOut: () {},
            links: const Stream.empty(),
            showTutorial: true,
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.byType(TutorialOverlay), findsNothing);
    });

    testWidgets('al 200 % no desborda y cumple las guías', (tester) async {
      phone(tester);
      await tester.pumpWidget(wrap(TutorialOverlay(gps: gps(), onDone: () {}), scale: 2));
      await tester.pumpAndSettle();
      await accessible(tester);
    });
  });

  group('Fuentes de Datos', () {
    Future<void> pump(WidgetTester tester, String? status, {List<int>? calls, double scale = 1}) async {
      await tester.pumpWidget(
        wrap(
          DataSourcesScreen(key: ValueKey(status), status: () async => status, connect: () async => calls?.add(1)),
          scale: scale,
        ),
      );
      await tester.pumpAndSettle();
    }

    testWidgets('sin conectar ofrece conectar Gmail', (tester) async {
      final calls = <int>[];
      await pump(tester, null, calls: calls);
      await tester.tap(find.text('Conectar Gmail'));
      expect(calls, [1]);
      // Sin reenvío de correos ni conexión bancaria, y texto honesto sobre el cifrado.
      for (final banned in ['Reenvío', 'Bancaria', 'militar', 'TLS']) {
        expect(find.textContaining(banned), findsNothing, reason: banned);
      }
      expect(find.textContaining('Tus datos viajan y se guardan cifrados'), findsOneWidget);
      // El backend mira remitente y asunto de todos para filtrar: no se dice «solo leemos».
      expect(find.textContaining('Solo guardamos los correos de tu banco'), findsOneWidget);
      expect(find.textContaining('Solo leemos'), findsNothing);
    });

    testWidgets('conectado no muestra botón; caído pide reconectar', (tester) async {
      await pump(tester, 'active');
      expect(find.textContaining('Conectado'), findsOneWidget);
      expect(find.byType(FilledButton), findsNothing);
      await pump(tester, 'needs_reconnect');
      expect(find.text('Reconectar Gmail'), findsOneWidget);
    });

    testWidgets('al 200 % no desborda y cumple las guías', (tester) async {
      phone(tester);
      await pump(tester, null, scale: 2);
      await accessible(tester);
    });
  });

  testWidgets('arranque: logo oficial, sin escudo, y al 200 % no desborda', (tester) async {
    phone(tester);
    await tester.pumpWidget(wrap(const LaunchScreen(), scale: 2));
    await tester.pump();
    expect(find.byType(AppLogo), findsOneWidget);
    expect(find.text('Finanzas Sin Filtro'), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('acceso: logo, máximo 3 campos, sin Apple ni FaceID, y accesible al 200 %', (tester) async {
    phone(tester);
    final auth = GoTrueClient(url: 'http://supabase.test/auth/v1', autoRefreshToken: false);
    await tester.pumpWidget(wrap(AuthScreen(auth: auth), scale: 2));
    await tester.pumpAndSettle();
    expect(find.byType(AppLogo), findsOneWidget);
    // «Continuar con Google» lleva la «G» oficial (normas de marca de Google).
    final google = find.widgetWithText(OutlinedButton, 'Continuar con Google');
    expect(
      find.descendant(
        of: google,
        matching: find.byWidgetPredicate(
          (w) => w is Image && (w.image as AssetImage).assetName == 'assets/images/google_g.png',
        ),
      ),
      findsOneWidget,
    );
    expect(find.byType(TextFormField).evaluate().length, lessThanOrEqualTo(3));
    for (final banned in ['Apple', 'FaceID', 'Términos']) {
      expect(find.textContaining(banned), findsNothing, reason: banned);
    }
    await accessible(tester);
  });
}
