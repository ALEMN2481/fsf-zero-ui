import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/api.dart';
import 'package:fsf_app/home_screen.dart';
import 'package:fsf_app/manual_expense.dart';
import 'package:fsf_app/money.dart' show nbsp;
import 'package:fsf_app/movements.dart';
import 'package:fsf_app/week_bars.dart';

import 'design_test.dart' show accessible, phone, wrap;
import 'home_test.dart' show backend, gps, now;
import 'support.dart';

/// Paso 15B: cabecera con burbujas, movimientos por día, gráfico semanal y gasto a mano.

Future<FakeBackend> home(WidgetTester tester, {String? name, String? email, double scale = 1}) async {
  final b = backend();
  b.routes['GET /me'] = (_) => {'id': 'u', 'gmail_status': 'active', 'display_name': name};
  await tester.pumpWidget(const SizedBox()); // pantalla nueva en cada llamada
  await tester.pumpWidget(
    wrap(
      HomeScreen(
        client: b.client,
        token: 't',
        onSignOut: () {},
        links: const Stream.empty(),
        now: () => now,
        email: email,
      ),
      scale: scale,
    ),
  );
  await tester.pumpAndSettle();
  return b;
}

void main() {
  group('cabecera', () {
    testWidgets('el nombre del perfil y, si no hay, el correo; Coach, bolsillos y ajustes a la derecha', (
      tester,
    ) async {
      await home(tester, name: 'Juan Sebastián', email: 'persona@ejemplo.com');
      expect(find.text('Juan Sebastián'), findsOneWidget);
      for (final tip in ['Abrir el Coach', 'Bolsillos', 'Ajustes']) {
        expect(find.byTooltip(tip), findsOneWidget, reason: tip);
      }
      expect(find.byType(TextField), findsNothing); // sin búsqueda
      await home(tester, email: 'persona@ejemplo.com');
      expect(find.text('persona@ejemplo.com'), findsOneWidget);
    });

    testWidgets('ajustes: Fuentes de datos, presupuesto y cerrar sesión', (tester) async {
      await home(tester, name: 'Ana');
      await tester.tap(find.byTooltip('Ajustes'));
      await tester.pumpAndSettle();
      for (final item in ['Fuentes de datos', 'Presupuesto', 'Cerrar sesión']) {
        expect(find.text(item), findsOneWidget, reason: item);
      }
    });

    testWidgets('el botón flotante es «+» (agregar gasto)', (tester) async {
      await home(tester, name: 'Ana');
      final fab = tester.widget<FloatingActionButton>(find.byType(FloatingActionButton));
      expect(fab.tooltip, 'Agregar gasto');
    });
  });

  group('movimientos por día', () {
    test('Hoy, Ayer, día de la semana y, si es de otro mes, el mes', () {
      expect(dayLabel('2026-11-25T12:45:00+00:00', now), 'Hoy');
      // 23:10 UTC del 24 = 18:10 del 24 en Colombia.
      expect(dayLabel('2026-11-24T23:10:00+00:00', now), 'Ayer');
      // 03:00 UTC del 25 = 22:00 del 24 en Colombia: sigue siendo ayer.
      expect(dayLabel('2026-11-25T03:00:00+00:00', now), 'Ayer');
      expect(dayLabel('2026-11-23T18:05:00+00:00', now), 'Lunes 23');
      expect(dayLabel('2026-10-31T15:00:00+00:00', now), 'Sábado 31 oct');
      expect(timeLabel('2026-11-24T23:10:00+00:00'), '18:10');
    });
  });

  group('gráfico de la semana', () {
    final days = (gps()['semana_dias'] as List).cast<Map<String, dynamic>>();

    testWidgets('el lector de pantalla lee el monto de cada día hasta hoy', (tester) async {
      final handle = tester.ensureSemantics();
      await tester.pumpWidget(
        wrap(
          Scaffold(
            body: WeekBars(days: days, now: now),
          ),
        ),
      );
      expect(
        find.bySemanticsLabel(
          'Gasto de la semana. lunes: \$${nbsp}32.000. martes: \$${nbsp}10.000. miércoles (hoy): \$${nbsp}23.500.',
        ),
        findsOneWidget,
      );
      handle.dispose();
    });

    testWidgets('la barra más alta es la del día que más se gastó; la letra de hoy va en negrita', (tester) async {
      await tester.pumpWidget(
        wrap(
          Scaffold(
            body: WeekBars(days: days, now: now),
          ),
        ),
      );
      double height(String day) => tester.getSize(find.byKey(ValueKey('barra_2026-11-$day'))).height;
      expect(height('23'), WeekBars.barsHeight);
      expect(height('24'), lessThan(height('25')));
      expect(height('29'), 0);
      final letters = tester.widgetList<Text>(find.descendant(of: find.byType(WeekBars), matching: find.byType(Text)));
      final bold = letters.where((t) => t.style?.fontWeight == FontWeight.w800).toList();
      expect(bold.length, 1);
      expect(bold.single.data, 'M'); // miércoles
    });

    testWidgets('al 200 % no desborda', (tester) async {
      phone(tester);
      await tester.pumpWidget(
        wrap(
          Scaffold(
            body: WeekBars(days: days, now: now),
          ),
          scale: 2,
        ),
      );
      expect(tester.takeException(), isNull);
    });
  });

  group('gasto a mano', () {
    Future<(FakeBackend, List<String?>)> open(WidgetTester tester) async {
      final b = backend();
      b.routes['POST /transactions'] = (_) => {'id': 'nuevo'};
      final results = <String?>[];
      await tester.pumpWidget(
        wrap(
          Builder(
            builder: (context) => FilledButton(
              onPressed: () async => results.add(
                await Navigator.of(context)
                    .push<String>(MaterialPageRoute(builder: (_) => ManualExpenseScreen(api: Api(b.client, 't')))),
              ),
              child: const Text('abrir'),
            ),
          ),
        ),
      );
      await tester.tap(find.text('abrir'));
      await tester.pumpAndSettle();
      return (b, results);
    }

    Future<void> next(WidgetTester tester) async {
      await tester.tap(find.text('Continuar'));
      await tester.pumpAndSettle();
    }

    testWidgets('3 pasos; sin la casilla no descuenta (ya se contó en el retiro)', (tester) async {
      final (b, results) = await open(tester);
      expect(find.text('¿Cuánto gastaste?'), findsOneWidget);
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Continuar')).onPressed, isNull);
      await tester.enterText(find.byKey(const Key('monto')), '12500');
      await tester.pump();
      expect(find.text('12.500'), findsOneWidget); // formateado mientras se escribe
      await next(tester);
      expect(find.text('¿En qué categoría?'), findsOneWidget);
      expect(find.text('Ingresos'), findsNothing); // solo gastos
      expect(tester.widget<FilledButton>(find.widgetWithText(FilledButton, 'Continuar')).onPressed, isNull);
      await tester.tap(find.text('Alimentos'));
      await tester.pump();
      await next(tester);
      expect(find.text('¿Dónde fue?'), findsOneWidget);
      await tester.enterText(find.byKey(const Key('comercio')), 'PANADERIA DEL BARRIO');
      await tester.tap(find.text('Guardar gasto'));
      await tester.pumpAndSettle();
      expect(b.body('POST /transactions'), {
        'monto': '12500',
        'category_id': 'c-ali',
        'comercio': 'PANADERIA DEL BARRIO',
        'fuera_de_retiro': false,
      });
      expect(results, [savedFromWithdrawal]);
    });

    testWidgets('con «No salió de un retiro» cuenta en el presupuesto; el comercio es opcional', (tester) async {
      final (b, results) = await open(tester);
      await tester.enterText(find.byKey(const Key('monto')), '1000000000000'); // 13 dígitos: no entra
      await tester.pump();
      expect(find.text('100.000.000.000'), findsNothing);
      await tester.enterText(find.byKey(const Key('monto')), '999999999999');
      await tester.pump();
      await next(tester);
      await tester.tap(find.text('Otros'));
      await tester.pump();
      await next(tester);
      await tester.tap(find.text('No salió de un retiro'));
      await tester.pump();
      await tester.tap(find.text('Guardar gasto'));
      await tester.pumpAndSettle();
      expect(b.body('POST /transactions'), {
        'monto': '999999999999', // exacto: sin double
        'category_id': 'c-otr',
        'fuera_de_retiro': true,
      });
      expect(results, [savedCounted]);
    });

    testWidgets('si falla, lo dice y no pierde lo escrito', (tester) async {
      final (b, results) = await open(tester);
      b.routes['POST /transactions'] = (_) => throw StateError('caído');
      await tester.enterText(find.byKey(const Key('monto')), '5000');
      await tester.pump();
      await next(tester);
      await tester.tap(find.text('Transporte'));
      await tester.pump();
      await next(tester);
      await tester.tap(find.text('Guardar gasto'));
      await tester.pumpAndSettle();
      expect(find.text('No se pudo guardar, inténtalo de nuevo'), findsOneWidget);
      expect(find.text('¿Dónde fue?'), findsOneWidget);
      expect(results, isEmpty);
    });

    testWidgets('atrás vuelve al paso anterior', (tester) async {
      await open(tester);
      await tester.enterText(find.byKey(const Key('monto')), '5000');
      await tester.pump();
      await next(tester);
      await tester.tap(find.byTooltip('Atrás'));
      await tester.pumpAndSettle();
      expect(find.text('¿Cuánto gastaste?'), findsOneWidget);
    });

    testWidgets('al 200 % cada paso cumple las guías', (tester) async {
      phone(tester);
      final b = backend();
      await tester.pumpWidget(wrap(ManualExpenseScreen(api: Api(b.client, 't')), scale: 2));
      await tester.pumpAndSettle();
      await accessible(tester);
    });
  });

  testWidgets('la principal con cabecera, gráfico y grupos al 200 % cumple las guías', (tester) async {
    phone(tester);
    await home(tester, name: 'Un nombre muy largo para probar que la burbuja lo recorta bien', scale: 2);
    await accessible(tester);
  });
}
