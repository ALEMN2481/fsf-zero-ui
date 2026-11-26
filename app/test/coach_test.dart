import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/api.dart';
import 'package:fsf_app/coach_screen.dart';
import 'package:fsf_app/home_screen.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

import 'design_test.dart' show accessible, phone, wrap;
import 'home_test.dart' show backend, now;
import 'support.dart';

/// Paso 13: chat del Coach. Las cifras vienen del backend como partes {texto, cifra}.

Map<String, dynamic> reply(String created) => {
  'rol': 'assistant',
  'partes': [
    {'texto': 'Hoy puedes gastar ', 'cifra': false},
    {'texto': '\$ 158.333', 'cifra': true},
    {'texto': ' sin salirte de tu plan.', 'cifra': false},
  ],
  'creado': created,
  'tipo': 'hoy',
  'fuente': 'llm',
};

final history = [
  {
    'rol': 'user',
    'partes': [
      {'texto': '¿Cuánto puedo gastar hoy?', 'cifra': false},
    ],
    'creado': '2026-11-25T14:41:00+00:00',
  },
  reply('2026-11-25T14:41:02+00:00'),
];

Future<FakeBackend> open(WidgetTester tester, {List<Object?>? messages, double scale = 1}) async {
  final b = FakeBackend({
    'GET /coach/messages': (_) => messages ?? const [],
    'POST /coach': (_) => reply('2026-11-25T17:00:00+00:00'),
    'DELETE /coach/messages': (_) => http.Response('', 204),
  });
  await tester.pumpWidget(
    wrap(
      CoachScreen(api: Api(b.client, 't'), now: () => now),
      scale: scale,
    ),
  );
  await tester.pumpAndSettle();
  return b;
}

/// El estilo del texto de [text] dentro de las burbujas (negrita para las cifras).
FontWeight? weightOf(WidgetTester tester, String text) {
  for (final rich in tester.widgetList<RichText>(find.byType(RichText))) {
    FontWeight? found;
    rich.text.visitChildren((span) {
      if (span is TextSpan && span.text == text) found = span.style?.fontWeight ?? FontWeight.w400;
      return found == null;
    });
    if (found != null) return found;
  }
  return null;
}

void main() {
  testWidgets('estado vacío: sugerencias, aviso y sin elementos de la plantilla', (tester) async {
    await open(tester);
    for (final s in coachSuggestions) {
      expect(find.text(s), findsOneWidget);
    }
    expect(find.text(coachDisclaimer), findsOneWidget);
    expect(find.text('Coach'), findsOneWidget);
    expect(find.text('Tu coach financiero'), findsOneWidget);
    for (final banned in ['Zero.AI', 'safety', 'Safety', 'Ask AI']) {
      expect(find.textContaining(banned), findsNothing, reason: banned);
    }
    expect(find.byIcon(Icons.search), findsNothing);
    expect(find.byIcon(Icons.filter_alt_outlined), findsNothing);
    expect(find.byIcon(Icons.settings_outlined), findsNothing);
  });

  testWidgets('una sugerencia se envía y la respuesta muestra la cifra en negrita', (tester) async {
    final b = await open(tester);
    await tester.tap(find.text(coachSuggestions.first));
    await tester.pumpAndSettle();
    expect(b.body('POST /coach'), {'mensaje': coachSuggestions.first});
    expect(find.text(coachSuggestions.first), findsOneWidget); // la burbuja del usuario
    expect(weightOf(tester, '\$ 158.333'), FontWeight.w700);
    expect(weightOf(tester, 'Hoy puedes gastar '), FontWeight.w400);
    expect(find.text(coachDisclaimer), findsNothing);
  });

  testWidgets('mientras responde se ve «Escribiendo…» y no se puede reenviar', (tester) async {
    final pending = Completer<http.Response>();
    var posts = 0;
    final client = MockClient((r) async {
      if (r.method == 'GET') return http.Response('[]', 200);
      posts++;
      return pending.future;
    });
    await tester.pumpWidget(wrap(CoachScreen(api: Api(client, 't'), now: () => now)));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '¿Cuánto me queda esta semana?');
    await tester.tap(find.byTooltip('Enviar'));
    await tester.pump();
    expect(find.text('Escribiendo…'), findsOneWidget);
    await tester.tap(find.byTooltip('Enviar'));
    expect(posts, 1);
    pending.complete(http.Response.bytes(utf8.encode(jsonEncode(reply('2026-11-25T17:00:00+00:00'))), 200));
    await tester.pumpAndSettle();
    expect(find.text('Escribiendo…'), findsNothing);
  });

  testWidgets('si el Coach falla, la pregunta vuelve al campo', (tester) async {
    final b = FakeBackend({
      'GET /coach/messages': (_) => const [],
      'POST /coach': (_) => http.Response('{"detail":"error"}', 502),
    });
    await tester.pumpWidget(wrap(CoachScreen(api: Api(b.client, 't'), now: () => now)));
    await tester.pumpAndSettle();
    await tester.enterText(find.byType(TextField), '¿Cuánto llevo en Alimentos?');
    await tester.tap(find.byTooltip('Enviar'));
    await tester.pumpAndSettle();
    expect(find.text('El Coach no pudo responder, inténtalo de nuevo'), findsOneWidget);
    expect(tester.widget<TextField>(find.byType(TextField)).controller!.text, '¿Cuánto llevo en Alimentos?');
  });

  testWidgets('historial y borrar la conversación', (tester) async {
    final b = await open(tester, messages: history);
    expect(find.text('¿Cuánto puedo gastar hoy?'), findsOneWidget);
    expect(weightOf(tester, '\$ 158.333'), FontWeight.w700);
    expect(find.text('hoy 09:41'), findsNWidgets(2));
    await tester.tap(find.byTooltip('Más opciones'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('Borrar conversación'));
    await tester.pumpAndSettle();
    expect(b.count('DELETE /coach/messages'), 1);
    expect(find.text(coachDisclaimer), findsOneWidget);
  });

  testWidgets('al 200 % no desborda y cumple las guías (vacío y con mensajes)', (tester) async {
    phone(tester);
    await open(tester, scale: 2);
    await accessible(tester);
    await open(tester, messages: history, scale: 2);
    await accessible(tester);
  });

  testWidgets('la principal tiene el botón ✦ que abre el Coach', (tester) async {
    final b = backend();
    b.routes['GET /coach/messages'] = (_) => const [];
    await tester.pumpWidget(
      wrap(HomeScreen(client: b.client, token: 't', onSignOut: () {}, links: const Stream.empty(), now: () => now)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byTooltip('Abrir el Coach'));
    await tester.pumpAndSettle();
    expect(find.byType(CoachScreen), findsOneWidget);
  });
}
