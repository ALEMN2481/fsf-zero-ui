import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter/services.dart';

/// Avisos push (Paso 14, D16). La notificación del sistema la arma el servicio nativo de Android
/// (`FsfMessagingService.kt`); aquí solo: token del dispositivo, permiso, mensajes con la app
/// abierta y abrir los ajustes. Interfaz propia para poder simularla en los tests.
abstract class Push {
  Future<String?> token();
  Stream<String> get tokenRefresh;

  /// Datos del aviso recibido con la app en primer plano (`tipo`, `title`, `transaction_id`…).
  Stream<Map<String, String>> get foreground;
  Future<bool> enabled();

  /// Android 13+: diálogo del sistema (POST_NOTIFICATIONS). Devuelve si quedaron activados.
  Future<bool> requestPermission();
  Future<void> openSettings();

  /// Ajustes de notificaciones de Android, donde se ocultan las cifras en la pantalla de bloqueo (D16).
  Future<void> openLockScreenSettings();
  Future<void> deleteToken();
}

// shortcut: token clásico de FCM (getToken/onTokenRefresh/deleteToken, obsoletos en
// firebase_messaging 17 a favor del FID con register/onRegistered). El backend envía por token con
// FCM HTTP v1, que sigue vigente; migrar al FID cuando FCM HTTP v1 documente el envío por FID.
// ignore_for_file: deprecated_member_use
class FirebasePush implements Push {
  FirebasePush([FirebaseMessaging? messaging]) : _fcm = messaging ?? FirebaseMessaging.instance;

  final FirebaseMessaging _fcm;
  static const _settings = MethodChannel('fsf/avisos');

  @override
  Future<String?> token() => _fcm.getToken();

  @override
  Stream<String> get tokenRefresh => _fcm.onTokenRefresh;

  @override
  Stream<Map<String, String>> get foreground =>
      FirebaseMessaging.onMessage.map((m) => m.data.map((k, v) => MapEntry(k, '$v')));

  @override
  Future<bool> enabled() async => _granted((await _fcm.getNotificationSettings()).authorizationStatus);

  @override
  Future<bool> requestPermission() async => _granted((await _fcm.requestPermission()).authorizationStatus);

  @override
  Future<void> openSettings() => _settings.invokeMethod('abrirAjustes');

  @override
  Future<void> openLockScreenSettings() => _settings.invokeMethod('abrirAjustesBloqueo');

  @override
  Future<void> deleteToken() => _fcm.deleteToken();

  static bool _granted(AuthorizationStatus s) =>
      s == AuthorizationStatus.authorized || s == AuthorizationStatus.provisional;
}
