import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/main.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';

void main() {
  testWidgets('muestra conectado cuando /health responde ok', (tester) async {
    final client = MockClient((_) async => http.Response('{"status":"ok"}', 200));
    await tester.pumpWidget(MainApp(client: client));
    await tester.pumpAndSettle();
    expect(find.text('Backend conectado'), findsOneWidget);
  });

  testWidgets('muestra no disponible cuando el backend falla', (tester) async {
    final client = MockClient((_) async => throw http.ClientException('sin red'));
    await tester.pumpWidget(MainApp(client: client));
    await tester.pumpAndSettle();
    expect(find.text('Backend no disponible'), findsOneWidget);
  });
}
