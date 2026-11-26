import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/home_screen.dart';
import 'package:fsf_app/money.dart' show nbsp;
import 'package:fsf_app/movements.dart';
import 'package:fsf_app/pockets_screen.dart';
import 'package:fsf_app/week_bars.dart';
import 'package:http/http.dart' as http;

import 'support.dart';

final now = DateTime.utc(2026, 11, 25, 17); // 12:00 en Colombia

Map<String, dynamic> gps({
  String hoy = '246666.00',
  String exceso = '0.00',
  String libre = '1580000.00',
  String plan = '266666.00',
  String manana = '270666.00',
  String revision = '10000.00',
}) => {
  'estado': 'ok',
  'periodo': {'inicio': '2026-11-01', 'fin': '2026-11-30', 'presupuesto': '3000000.00', 'renovado': false},
  'dias_restantes': 6,
  'saldo_libre': libre,
  'disponible_hoy': hoy,
  'exceso': exceso,
  'diario_plan': plan,
  'diario_desde_manana': manana,
  'disponible_semana': '1313330.00',
  'en_revision': revision,
  'reservado': '350000.00',
  // Paso 15B: lo gastado cada día de lunes 23 a domingo 29 (hoy es el miércoles 25).
  'semana_dias': [
    {'fecha': '2026-11-23', 'gastado': '32000.00'},
    {'fecha': '2026-11-24', 'gastado': '10000.00'},
    {'fecha': '2026-11-25', 'gastado': '23500.00'},
    for (final d in ['26', '27', '28', '29']) {'fecha': '2026-11-$d', 'gastado': '0.00'},
  ],
};

final movements = [
  {
    'id': 't1',
    'monto': '23500.00',
    'direccion': 'expense',
    'estado': 'confirmed',
    'comercio': 'PANADERIA EJEMPLO',
    'fecha': '2026-11-25T12:45:00+00:00',
    'categoria': 'Alimentos',
    'categoria_id': 'c-ali',
    'tipo': 'gasto',
  },
  {
    'id': 't2',
    'monto': '10000.00',
    'direccion': 'expense',
    'estado': 'pending_review',
    'comercio': 'TIENDA DE BARRIO EJEMPLO',
    'fecha': '2026-11-24T23:10:00+00:00',
    'categoria': 'Otros',
    'categoria_id': 'c-otr',
    'tipo': 'gasto',
  },
  {
    'id': 't3',
    'monto': '32000.00',
    'direccion': 'expense',
    'estado': 'confirmed',
    'comercio': 'RESTAURANTE EJEMPLO SAS',
    'fecha': '2026-11-23T18:05:00+00:00',
    'categoria': 'Alimentos',
    'categoria_id': 'c-ali',
    'tipo': 'efectivo_factura',
  },
];

FakeBackend backend({Map<String, dynamic>? state, List<Map<String, dynamic>>? list, String gmail = 'active'}) =>
    FakeBackend({
      'GET /gps': (_) => state ?? gps(),
      'GET /movements': (_) => list ?? movements,
      'GET /me': (_) => {'id': 'u', 'gmail_status': gmail},
      'GET /categories': (_) => [
        {'id': 'c-ali', 'name': 'Alimentos', 'user_id': null},
        {'id': 'c-otr', 'name': 'Otros', 'user_id': null},
        {'id': 'c-tra', 'name': 'Transporte', 'user_id': null},
        {'id': 'c-ing', 'name': 'Ingresos', 'user_id': null},
      ],
      'GET /budgets/suggestion': (_) => {
        'gasto_mes_anterior': '2850000.00',
        'ingresos_mes_anterior': '3500000.00',
        'sugerido': '2850000.00',
      },
      'POST /budgets': (_) => {'id': 'b'},
      'POST /transactions/t2/confirm': (_) => {'id': 't2', 'estado': 'confirmed'},
      'POST /transactions/t2/dismiss': (_) => {'id': 't2', 'estado': 'dismissed'},
      'PATCH /transactions/t2/category': (_) => {'id': 't2'},
      'POST /gmail/connect': (_) => {'url': 'https://accounts.google.com/o/oauth2/v2/auth?x=1'},
      'GET /pockets': (_) => {
        'total': '500000.00',
        'bolsillos': [
          {'id': 'p1', 'name': 'Viaje', 'target_amount': '1000000.00', 'saldo': '500000.00', 'porcentaje': 50},
        ],
      },
    });

Widget app(FakeBackend b, {double scale = 1, Stream<void>? changes, List<Uri>? opened}) => MaterialApp(
  home: MediaQuery(
    data: MediaQueryData(textScaler: TextScaler.linear(scale)),
    child: HomeScreen(
      client: b.client,
      token: 'jwt-usuario',
      onSignOut: () {},
      links: const Stream.empty(),
      now: () => now,
      changes: changes == null ? null : () => changes,
      openUrl: (url) async {
        opened?.add(url);
        return true;
      },
    ),
  ),
);

String plain(String s) => s.replaceAll(nbsp, ' ');
Finder textContaining(String s) => find.byWidgetPredicate((w) => w is Text && plain(w.data ?? '').contains(s));

void main() {
  testWidgets('1 · una cifra grande en el centro y pocas líneas debajo', (tester) async {
    tall(tester);
    final b = backend();
    await tester.pumpWidget(app(b));
    await tester.pumpAndSettle();
    expect(find.text('HOY PUEDES GASTAR'), findsOneWidget);
    expect(plain(tester.widget<Text>(find.byKey(const Key('disponible_hoy'))).data!), '\$ 246.666');
    expect(textContaining('Te quedan esta semana \$ 1.313.330'), findsOneWidget);
    expect(textContaining('Te quedan este mes \$ 1.580.000 · 6 días'), findsOneWidget);
    expect(textContaining('Incluye \$ 10.000 por confirmar'), findsOneWidget);
    expect(find.byKey(const Key('gps')), findsNothing); // sin exceso no hay aviso GPS
    expect(find.text(pendingLabel), findsOneWidget);
    expect(textContaining('efectivo, ya contado en el retiro'), findsOneWidget);
    expect(textContaining('-\$ 23.500'), findsOneWidget);
    // Agrupados por día (Paso 15B), en hora de Colombia; dentro del grupo, solo la hora.
    expect(find.text('Hoy'), findsOneWidget);
    expect(find.text('Ayer'), findsOneWidget);
    expect(find.text('Lunes 23'), findsOneWidget);
    expect(find.text('07:45'), findsOneWidget);
    expect(find.text('18:10'), findsOneWidget);
    expect(textContaining('Reservado'), findsOneWidget);
    expect(plain(tester.widget<Text>(find.byKey(const Key('reservado'))).data!), '\$ 350.000');
    expect(b.sent.every((r) => r.headers['Authorization'] == 'Bearer jwt-usuario'), isTrue);
  });

  testWidgets('2 · al pasarse: negativo, texto neutral y el diario que baja', (tester) async {
    await tester.pumpWidget(
      app(
        backend(
          state: gps(hoy: '-66666.00', exceso: '66666.00', plan: '500000.00', manana: '486666.00'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(find.text('HOY'), findsOneWidget);
    expect(plain(tester.widget<Text>(find.byKey(const Key('disponible_hoy'))).data!), '-\$ 66.666');
    expect(textContaining('Hoy fuiste \$ 66.666 más allá de tu diario.'), findsOneWidget);
    expect(textContaining('Tu diario de mañana baja de \$ 500.000 a \$ 486.666.'), findsOneWidget);
    for (final word in ['mal', 'error', 'cuidado', 'excediste', '!']) {
      expect(textContaining(word), findsNothing, reason: 'sin juicio: "$word"');
    }
  });

  testWidgets('2b · mes sobregirado: lo dice una vez y el diario queda en 0', (tester) async {
    await tester.pumpWidget(
      app(
        backend(
          state: gps(hoy: '0.00', libre: '-100000.00', manana: '0.00'),
        ),
      ),
    );
    await tester.pumpAndSettle();
    expect(
      textContaining(
        'Este mes vas \$ 100.000 por encima de lo planeado. Tu diario queda en \$ 0 hasta el próximo mes.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('3 · sin presupuesto: un campo, prellenado con el gasto y las dos referencias', (tester) async {
    final b = backend(state: {'estado': 'sin_presupuesto', 'hoy': '2026-11-25'});
    await tester.pumpWidget(app(b));
    await tester.pumpAndSettle();
    expect(find.byType(TextField), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, '2.850.000');
    expect(textContaining('El mes pasado gastaste \$ 2.850.000 y te entraron \$ 3.500.000.'), findsOneWidget);
    expect(find.text('Se renueva solo cada mes.'), findsOneWidget);

    await tester.enterText(find.byType(TextField), 'mil');
    await tester.tap(find.text('Empezar'));
    await tester.pumpAndSettle();
    expect(b.count('POST /budgets'), 0);
    await tester.enterText(find.byType(TextField), '2.500.000');
    await tester.tap(find.text('Empezar'));
    await tester.pumpAndSettle();
    expect(b.body('POST /budgets'), {'amount': '2500000'}); // texto, nunca double
  });

  testWidgets('3b · sin gasto previo: el campo vacío y los ingresos como referencia', (tester) async {
    final b = backend(state: {'estado': 'sin_presupuesto'});
    b.routes['GET /budgets/suggestion'] = (_) => {
      'gasto_mes_anterior': '0.00',
      'ingresos_mes_anterior': '3500000.00',
      'sugerido': null,
    };
    await tester.pumpWidget(app(b));
    await tester.pumpAndSettle();
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, isEmpty);
    expect(textContaining('El mes pasado te entraron \$ 3.500.000.'), findsOneWidget);
    expect(textContaining('gastaste'), findsNothing);
  });

  testWidgets('4 · estado vacío con el texto del documento y acceso al correo', (tester) async {
    tall(tester);
    final opened = <Uri>[];
    final b = backend(list: [], gmail: 'none');
    await tester.pumpWidget(app(b, opened: opened));
    await tester.pumpAndSettle();
    expect(find.text(emptyText), findsOneWidget);
    await tester.tap(find.widgetWithText(FilledButton, 'Conectar correo'));
    await tester.pumpAndSettle();
    expect(b.count('POST /gmail/connect'), 1);
    expect(opened.single.host, 'accounts.google.com');
  });

  testWidgets('4b · con Gmail conectado el estado vacío no ofrece conectar', (tester) async {
    tall(tester);
    await tester.pumpWidget(app(backend(list: [])));
    await tester.pumpAndSettle();
    expect(find.text(emptyText), findsOneWidget);
    expect(find.text('Conectar correo'), findsNothing);
  });

  testWidgets('5 · por confirmar: categoría con un toque, confirmar y descartar', (tester) async {
    tall(tester);
    final b = backend();
    await tester.pumpWidget(app(b));
    await tester.pumpAndSettle();
    await tester.tap(find.text('TIENDA DE BARRIO EJEMPLO'));
    await tester.pumpAndSettle();
    expect(textContaining('Por confirmar'), findsOneWidget);
    await tester.tap(find.widgetWithText(CategoryOption, 'Alimentos'));
    await tester.pumpAndSettle();
    expect(b.body('PATCH /transactions/t2/category'), {'category_id': 'c-ali'});

    final loads = b.count('GET /gps');
    await tester.tap(find.text('Confirmar'));
    await tester.pumpAndSettle();
    expect(b.count('POST /transactions/t2/confirm'), 1);
    expect(b.count('GET /gps'), greaterThan(loads)); // la pantalla se refresca
    expect(find.text('Confirmar'), findsNothing); // la hoja se cerró

    await tester.tap(find.text('TIENDA DE BARRIO EJEMPLO'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('No es un gasto mío'));
    await tester.pumpAndSettle();
    expect(b.count('POST /transactions/t2/dismiss'), 1);
  });

  testWidgets('5b · un movimiento confirmado solo deja cambiar la categoría', (tester) async {
    tall(tester);
    await tester.pumpWidget(app(backend()));
    await tester.pumpAndSettle();
    await tester.tap(find.text('PANADERIA EJEMPLO'));
    await tester.pumpAndSettle();
    expect(find.byType(CategoryOption), findsNWidgets(3));
    expect(find.widgetWithText(CategoryOption, 'Ingresos'), findsNothing); // un gasto no es un ingreso
    expect(find.text('Confirmar'), findsNothing);
    expect(find.text('No es un gasto mío'), findsNothing);
  });

  group('6 · bolsillos', () {
    Future<FakeBackend> openPockets(WidgetTester tester, {Object? moveAnswer}) async {
      final b = backend();
      b.routes['POST /pockets'] = (_) => {'id': 'p2', 'name': 'Moto'};
      b.routes['POST /pockets/p1/movements'] = (_) => moveAnswer ?? {'pocket_id': 'p1', 'saldo': '600000.00'};
      b.routes['POST /pockets/p2/movements'] = (_) => moveAnswer ?? {'pocket_id': 'p2', 'saldo': '1.00'};
      await tester.pumpWidget(app(b));
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Bolsillos'));
      await tester.pumpAndSettle();
      return b;
    }

    final overdraft = http.Response(
      jsonEncode({
        'detail': {'motivo': 'sobregiro', 'maximo': '800000.00'},
      }),
      409,
    );

    testWidgets('lista con barra de progreso plana', (tester) async {
      await openPockets(tester);
      expect(find.text('Viaje'), findsOneWidget);
      expect(textContaining('\$ 500.000'), findsNWidgets(2)); // total y saldo del bolsillo
      expect(textContaining('meta: \$ 1.000.000'), findsOneWidget);
      expect(find.text('50 %'), findsOneWidget); // el % viene del backend
      expect(tester.widget<LinearProgressIndicator>(find.byType(LinearProgressIndicator)).value, 0.5);
    });

    testWidgets('crear pide 2 campos; la meta es opcional y va oculta', (tester) async {
      final b = await openPockets(tester);
      await tester.tap(find.byTooltip('Crear bolsillo'));
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsNWidgets(2));
      await tester.enterText(find.widgetWithText(TextField, 'Nombre, por ejemplo Viaje'), 'Moto');
      await tester.enterText(find.widgetWithText(TextField, 'Monto a reservar'), '100.000');
      await tester.tap(find.text('Crear'));
      await tester.pumpAndSettle();
      expect(b.body('POST /pockets'), {'name': 'Moto'});
      expect(b.body('POST /pockets/p2/movements'), {'amount': '100000'});
    });

    testWidgets('apartar pide 1 campo y, si se pasa, sugiere el máximo (CU-05)', (tester) async {
      final b = await openPockets(tester, moveAnswer: overdraft);
      await tester.tap(find.text('Apartar'));
      await tester.pumpAndSettle();
      expect(find.byType(TextField), findsOneWidget);
      await tester.enterText(find.byType(TextField), '900.000');
      await tester.tap(find.widgetWithText(FilledButton, 'Apartar'));
      await tester.pumpAndSettle();
      expect(textContaining('Puedes apartar hasta \$ 800.000'), findsOneWidget);
      b.routes['POST /pockets/p1/movements'] = (_) => {'pocket_id': 'p1', 'saldo': '1300000.00'};
      await tester.tap(
        find.widgetWithText(
          FilledButton,
          'Apartar ${'\$'}$nbsp'
          '800.000',
        ),
      );
      await tester.pumpAndSettle();
      expect(b.body('POST /pockets/p1/movements'), {'amount': '800000.00'});
    });

    testWidgets('retirar envía el monto en negativo', (tester) async {
      final b = await openPockets(tester);
      await tester.tap(find.text('Retirar'));
      await tester.pumpAndSettle();
      await tester.enterText(find.byType(TextField), '50.000');
      await tester.tap(find.widgetWithText(FilledButton, 'Retirar'));
      await tester.pumpAndSettle();
      expect(b.body('POST /pockets/p1/movements'), {'amount': '-50000'});
    });
  });

  testWidgets('Realtime: un cambio en los movimientos vuelve a pedir las cifras', (tester) async {
    final b = backend(), changes = StreamController<void>();
    await tester.pumpWidget(app(b, changes: changes.stream));
    await tester.pumpAndSettle();
    expect(b.count('GET /gps'), 1);
    changes.add(null);
    await tester.pumpAndSettle();
    expect(b.count('GET /gps'), 2);
    tester.binding.handleAppLifecycleStateChanged(AppLifecycleState.resumed);
    await tester.pumpAndSettle();
    expect(b.count('GET /gps'), 3); // también al volver a la app
    await changes.close();
  });

  testWidgets('si el backend falla, lo dice y deja reintentar', (tester) async {
    final b = FakeBackend({});
    await tester.pumpWidget(app(b));
    await tester.pumpAndSettle();
    expect(find.text(loadError), findsOneWidget);
    expect(find.text('Reintentar'), findsOneWidget);
  });

  group('Zero-UI y accesibilidad (RQN 05)', () {
    testWidgets('sin tablas; el único gráfico es el de la semana (D13)', (tester) async {
      await tester.pumpWidget(app(backend()));
      await tester.pumpAndSettle();
      expect(find.byType(Table), findsNothing);
      expect(find.byType(DataTable), findsNothing);
      expect(find.byType(WeekBars), findsOneWidget);
      // Ningún otro dibujo: ni CustomPaint fuera de los del propio framework ni widgets «Chart».
      expect(
        find.byType(CustomPaint).evaluate().where((e) => e.widget.runtimeType.toString().contains('Chart')),
        isEmpty,
      );
      expect(find.descendant(of: find.byType(WeekBars), matching: find.byType(CustomPaint)), findsNothing);
      final pubspec = File('pubspec.yaml').readAsStringSync();
      for (final chart in ['fl_chart', 'charts_flutter', 'syncfusion_flutter_charts', 'graphic']) {
        expect(pubspec.contains(chart), isFalse, reason: chart);
      }
    });

    for (final (name, state) in [
      ('principal', gps()),
      ('pasado', gps(hoy: '-66666.00', exceso: '66666.00', plan: '500000.00', manana: '486666.00')),
      ('sin presupuesto', <String, dynamic>{'estado': 'sin_presupuesto'}),
    ]) {
      testWidgets('$name: se ve con el texto del sistema al 200 % y botones de 48×48', (tester) async {
        tester.view.physicalSize = const Size(1080, 2340); // teléfono típico
        tester.view.devicePixelRatio = 2.75;
        addTearDown(tester.view.reset);
        await tester.pumpWidget(app(backend(state: state), scale: 2));
        await tester.pumpAndSettle();
        expect(tester.takeException(), isNull); // sin desbordes
        await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
        await expectLater(tester, meetsGuideline(labeledTapTargetGuideline));
        await expectLater(tester, meetsGuideline(textContrastGuideline));
      });
    }

    testWidgets('la hoja del movimiento y los bolsillos también cumplen al 200 %', (tester) async {
      tester.view.physicalSize = const Size(1080, 2340);
      tester.view.devicePixelRatio = 2.75;
      addTearDown(tester.view.reset);
      await tester.pumpWidget(app(backend(), scale: 2));
      await tester.pumpAndSettle();
      await tester.scrollUntilVisible(find.text('TIENDA DE BARRIO EJEMPLO'), 300);
      await tester.ensureVisible(find.text('TIENDA DE BARRIO EJEMPLO')); // entera, no solo asomada
      await tester.pumpAndSettle();
      await tester.tap(find.text('TIENDA DE BARRIO EJEMPLO'));
      await tester.pumpAndSettle();
      expect(find.byType(MovementSheet), findsOneWidget);
      expect(tester.takeException(), isNull);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      Navigator.of(tester.element(find.byType(MovementSheet))).pop();
      await tester.pumpAndSettle();
      await tester.tap(find.byTooltip('Bolsillos'));
      await tester.pumpAndSettle();
      expect(tester.takeException(), isNull);
      await expectLater(tester, meetsGuideline(androidTapTargetGuideline));
      expect(find.byType(PocketCard), findsOneWidget);
    });
  });

  testWidgets('5c · en un ingreso sí se ofrece «Ingresos»', (tester) async {
    tall(tester);
    final income = {
      ...movements.first,
      'id': 't9',
      'direccion': 'income',
      'tipo': 'ingreso',
      'comercio': 'EMPRESA EMPLEADORA EJEMPLO SAS',
      'categoria': 'Ingresos',
      'categoria_id': 'c-ing',
    };
    await tester.pumpWidget(app(backend(list: [income])));
    await tester.pumpAndSettle();
    await tester.tap(find.text('EMPRESA EMPLEADORA EJEMPLO SAS'));
    await tester.pumpAndSettle();
    expect(find.widgetWithText(CategoryOption, 'Ingresos'), findsOneWidget);
    expect(find.byType(CategoryOption), findsNWidgets(4));
  });
}
