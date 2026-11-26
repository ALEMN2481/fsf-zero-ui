import 'dart:convert';

import 'package:http/http.dart' as http;

// 10.0.2.2 = localhost del PC visto desde el emulador Android. Otro destino: --dart-define=API_URL=...
const apiUrl = String.fromEnvironment('API_URL', defaultValue: 'http://10.0.2.2:8000');

/// La primera llamada puede tardar más (el backend descarga el JWKS para validar el token).
const apiTimeout = Duration(seconds: 10);

/// El Coach espera al LLM local: con el modelo fuera de memoria tarda unos 12 s (Paso 13).
const coachTimeout = Duration(seconds: 45);

/// Respuesta de error del backend: [detail] es el texto o el objeto `detail` de FastAPI.
class ApiError implements Exception {
  ApiError(this.status, this.detail);
  final int status;
  final Object? detail;

  /// Campo de un detalle con forma de objeto (p. ej. `maximo` del sobregiro de un bolsillo).
  String? field(String name) => detail is Map ? (detail as Map)[name]?.toString() : null;

  @override
  String toString() => 'ApiError($status, $detail)';
}

/// Cliente del backend con el JWT del usuario. Los montos llegan y se envían como texto.
class Api {
  Api(this.client, this.token);

  final http.Client client;
  final String token;

  Map<String, String> get _headers => {'Authorization': 'Bearer $token', 'Content-Type': 'application/json'};

  Future<dynamic> get(String path) => _send(client.get(Uri.parse('$apiUrl$path'), headers: _headers));

  Future<dynamic> post(String path, [Object? body, Duration timeout = apiTimeout]) => _send(
    client.post(Uri.parse('$apiUrl$path'), headers: _headers, body: body == null ? null : jsonEncode(body)),
    timeout,
  );

  Future<dynamic> delete(String path, [Object? body]) =>
      _send(client.delete(Uri.parse('$apiUrl$path'), headers: _headers, body: body == null ? null : jsonEncode(body)));

  Future<dynamic> patch(String path, Object body) =>
      _send(client.patch(Uri.parse('$apiUrl$path'), headers: _headers, body: jsonEncode(body)));

  Future<dynamic> _send(Future<http.Response> request, [Duration timeout = apiTimeout]) async {
    final res = await request.timeout(timeout);
    final body = res.body.isEmpty ? null : jsonDecode(utf8.decode(res.bodyBytes));
    if (res.statusCode >= 300) throw ApiError(res.statusCode, body is Map ? body['detail'] : body);
    return body;
  }
}
