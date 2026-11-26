/// Capturas de las pantallas 1–6 (Paso 12) con golden tests y la fuente real (Roboto).
///
/// Datos: respuestas reales del backend local para la cuenta demo, sembrada con el conjunto del
/// supervisor (test/goldens/data). Generar o actualizar:
///     flutter test --tags golden --update-goldens
/// El render depende del sistema operativo: la CI los excluye (--exclude-tags golden).
@Tags(['golden'])
library;

import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart' show FontLoader;
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/auth_screen.dart';
import 'package:fsf_app/data_sources_screen.dart';
import 'package:fsf_app/home_screen.dart';
import 'package:fsf_app/launch_screen.dart';
import 'package:fsf_app/theme.dart';
import 'package:supabase_flutter/supabase_flutter.dart' show GoTrueClient;

import 'support.dart';

Map<String, dynamic> load(String name) =>
    jsonDecode(File('test/goldens/data/$name.json').readAsStringSync()) as Map<String, dynamic>;

/// Las fuentes de la app (Inter y Unbounded, en assets/fonts) y los iconos de Material del SDK:
/// sin ellas el texto sale como cuadros.
Future<void> loadFonts() async {
  Future<ByteData> asset(String path) async => ByteData.sublistView(await File(path).readAsBytes());
  final inter = FontLoader('Inter');
  for (final w in ['Regular', 'Medium', 'SemiBold', 'Bold']) {
    inter.addFont(asset('assets/fonts/inter/Inter-$w.ttf'));
  }
  await inter.load();
  final unbounded = FontLoader('Unbounded');
  for (final w in ['Medium', 'Bold']) {
    unbounded.addFont(asset('assets/fonts/unbounded/Unbounded-$w.ttf'));
  }
  await unbounded.load();
  final root =
      Platform.environment['FLUTTER_ROOT'] ??
      // flutter_tester vive en <flutter>/bin/cache/artifacts/engine/<plataforma>/
      File(Platform.resolvedExecutable).parent.parent.parent.parent.parent.parent.path;
  final dir = '$root/bin/cache/artifacts/material_fonts';
  Future<ByteData> bytes(String file) async => ByteData.sublistView(await File('$dir/$file').readAsBytes());
  final roboto = FontLoader('Roboto');
  for (final weight in ['light', 'regular', 'medium', 'bold']) {
    roboto.addFont(bytes('roboto-$weight.ttf'));
  }
  await roboto.load();
  await (FontLoader('MaterialIcons')..addFont(bytes('materialicons-regular.otf'))).load();
}

final demo = load('demo'), over = load('demo_over');
final now = DateTime.utc(2026, 11, 25, 22); // 17:00 en Colombia, como cuando se tomaron los datos

FakeBackend backend({Object? gps, Object? movements, String gmail = 'active'}) => FakeBackend({
  'GET /gps': (_) => gps ?? demo['gps'],
  'GET /movements': (_) => movements ?? demo['movements'],
  'GET /me': (_) => {'id': 'demo', 'gmail_status': gmail},
  'GET /categories': (_) => demo['categories'],
  'GET /budgets/suggestion': (_) => demo['suggestion'],
  'GET /pockets': (_) => demo['pockets'],
});

Future<void> shoot(WidgetTester tester, FakeBackend b, String name, {double scale = 1, bool tutorial = false}) async {
  await shootWidget(
    tester,
    HomeScreen(
      client: b.client,
      token: 'demo',
      onSignOut: () {},
      links: const Stream.empty(),
      now: () => now,
      showTutorial: tutorial,
    ),
    scale: scale,
  );
}

Future<void> shootWidget(WidgetTester tester, Widget screen, {double scale = 1, bool settle = true}) async {
  tester.view.physicalSize = const Size(1080, 2340); // teléfono típico (393×851 lógicos)
  tester.view.devicePixelRatio = 2.75;
  addTearDown(tester.view.reset);
  // flutter_test dibuja las sombras como un contorno negro sólido; en las capturas, como en el
  // dispositivo, se ven las reales (se restaura al terminar cada captura).
  debugDisableShadows = false;
  await tester.pumpWidget(
    MaterialApp(
      debugShowCheckedModeBanner: false,
      theme: fsfTheme(),
      home: MediaQuery(
        data: MediaQueryData(size: const Size(1080 / 2.75, 2340 / 2.75), textScaler: TextScaler.linear(scale)),
        child: screen,
      ),
    ),
  );
  // La barra del arranque es indefinida: nunca se asienta, se avanza un tiempo fijo.
  if (settle) {
    await tester.pumpAndSettle();
  } else {
    // Las imágenes se decodifican fuera del reloj falso del test: se precargan de verdad.
    await tester.runAsync(
      () => precacheImage(const AssetImage('assets/images/logo.png'), tester.element(find.byWidget(screen))),
    );
    await tester.pump(const Duration(milliseconds: 600));
  }
}

Future<void> golden(WidgetTester tester, String name) async {
  try {
    await expectLater(find.byType(MaterialApp), matchesGoldenFile('goldens/$name.png'));
  } finally {
    debugDisableShadows = true;
  }
}

void main() {
  setUpAll(loadFonts);

  testWidgets('1 · principal', (tester) async {
    await shoot(tester, backend(), '1');
    await golden(tester, '1_principal');
  });

  testWidgets('1b · principal con el texto al 200 %', (tester) async {
    await shoot(tester, backend(), '1b', scale: 2);
    await golden(tester, '1b_principal_texto_200');
  });

  testWidgets('2 · principal en negativo (efecto GPS)', (tester) async {
    await shoot(tester, backend(gps: over['gps'], movements: over['movements']), '2');
    await golden(tester, '2_negativo');
  });

  testWidgets('2b · negativo con el texto al 200 %', (tester) async {
    await shoot(tester, backend(gps: over['gps'], movements: over['movements']), '2b', scale: 2);
    await golden(tester, '2b_negativo_texto_200');
  });

  testWidgets('3 · sin presupuesto', (tester) async {
    await shoot(tester, backend(gps: {'estado': 'sin_presupuesto'}), '3');
    await golden(tester, '3_sin_presupuesto');
  });

  testWidgets('4 · estado vacío', (tester) async {
    await shoot(tester, backend(movements: const [], gmail: 'none'), '4');
    await golden(tester, '4_estado_vacio');
  });

  testWidgets('5 · hoja de un movimiento por confirmar', (tester) async {
    await shoot(tester, backend(), '5');
    final pending = find.text('FERRETERIA EJEMPLO SAS');
    await tester.scrollUntilVisible(pending, 300);
    await tester.tap(pending);
    await tester.pumpAndSettle();
    await golden(tester, '5_movimiento_por_confirmar');
  });

  testWidgets('6 · bolsillos', (tester) async {
    await shoot(tester, backend(), '6');
    await tester.tap(find.byTooltip('Bolsillos'));
    await tester.pumpAndSettle();
    await golden(tester, '6_bolsillos');
  });

  testWidgets('7 · arranque', (tester) async {
    await shootWidget(tester, const LaunchScreen(), settle: false);
    await golden(tester, '7_arranque');
  });

  testWidgets('8 · acceso', (tester) async {
    final auth = GoTrueClient(url: 'http://supabase.test/auth/v1', autoRefreshToken: false);
    await shootWidget(tester, AuthScreen(auth: auth));
    await golden(tester, '8_acceso');
  });

  testWidgets('9 · tutorial «Primer vistazo»', (tester) async {
    await shoot(tester, backend(), '9', tutorial: true);
    await golden(tester, '9_tutorial');
  });

  testWidgets('10 · Fuentes de Datos', (tester) async {
    await shootWidget(tester, DataSourcesScreen(status: () async => null, connect: () async {}));
    await golden(tester, '10_fuentes_de_datos');
  });
}
