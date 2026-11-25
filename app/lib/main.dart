import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:http/http.dart' as http;
import 'package:local_auth/local_auth.dart';
import 'package:local_auth_android/local_auth_android.dart';
import 'package:local_auth_darwin/local_auth_darwin.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import 'auth_screen.dart';
import 'home_screen.dart';
import 'session_storage.dart';

// Se pasan con --dart-define-from-file=.env.json (ver env.example.json); la anon key es pública.
const supabaseUrl = String.fromEnvironment('SUPABASE_URL');
const supabaseAnonKey = String.fromEnvironment('SUPABASE_ANON_KEY');

/// Tiempo en segundo plano a partir del cual se vuelve a pedir el desbloqueo.
const lockAfter = Duration(minutes: 5);
const lockWarning = 'Activa un bloqueo de pantalla para proteger tu información';
const _lockWarningShownKey = 'lock_warning_shown';

/// Textos del diálogo del sistema; sin ellos Android e iOS los muestran en inglés.
const unlockMessages = <AuthMessages>[
  AndroidAuthMessages(
    signInTitle: 'Finanzas Sin Filtro',
    signInHint: 'Usa tu huella o el bloqueo de pantalla',
    cancelButton: 'Cancelar',
  ),
  IOSAuthMessages(cancelButton: 'Cancelar', localizedFallbackTitle: 'Usar código'),
];

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  const storage = FlutterSecureStorage();
  const sessionStore = SecureSessionStorage(storage);
  await Supabase.initialize(
    url: supabaseUrl,
    publishableKey: supabaseAnonKey,
    authOptions: const FlutterAuthClientOptions(localStorage: sessionStore),
  );
  runApp(
    FsfApp(
      auth: Supabase.instance.client.auth,
      sessionStore: sessionStore,
      storage: storage,
      deviceLock: LocalAuthentication(),
      client: http.Client(),
    ),
  );
}

class FsfApp extends StatefulWidget {
  const FsfApp({
    super.key,
    required this.auth,
    required this.sessionStore,
    required this.storage,
    required this.deviceLock,
    required this.client,
    this.now = DateTime.now,
    this.openUrl = openInBrowser,
  });

  final GoTrueClient auth;
  final LocalStorage sessionStore;
  final FlutterSecureStorage storage;
  final LocalAuthentication deviceLock;
  final http.Client client;
  final DateTime Function() now;
  final Future<bool> Function(Uri url) openUrl;

  @override
  State<FsfApp> createState() => _FsfAppState();
}

class _FsfAppState extends State<FsfApp> with WidgetsBindingObserver {
  final _messenger = GlobalKey<ScaffoldMessengerState>();
  late final StreamSubscription<AuthState> _authSub;
  bool _locked = false;
  DateTime? _backgroundSince;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _authSub = widget.auth.onAuthStateChange.listen((state) {
      if (!mounted) return;
      setState(() {});
      if (state.event == AuthChangeEvent.signedIn) _warnIfUnprotected();
    });
    if (widget.auth.currentSession != null) _lock(); // al abrir la app con sesión guardada
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _authSub.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused) {
      _backgroundSince ??= widget.now();
    } else if (state == AppLifecycleState.resumed) {
      final since = _backgroundSince;
      _backgroundSince = null;
      if (since != null && widget.now().difference(since) >= lockAfter && widget.auth.currentSession != null) {
        _lock();
      }
    }
  }

  /// Bloquea en el acto (sin mostrar datos) y luego pide biometría o PIN, si el dispositivo tiene.
  Future<void> _lock() async {
    setState(() => _locked = true);
    if (await _deviceProtected()) {
      await _unlock();
    } else {
      // Sin biometría ni PIN no hay con qué bloquear: se avisa una vez.
      if (mounted) setState(() => _locked = false);
      await _warnOnce();
    }
  }

  Future<void> _unlock() async {
    var ok = false;
    try {
      ok = await widget.deviceLock.authenticate(
        localizedReason: 'Desbloquea la app para ver tu información',
        authMessages: unlockMessages,
      );
    } on LocalAuthException catch (e) {
      if (e.code == LocalAuthExceptionCode.noCredentialsSet) {
        ok = true; // se quitó el bloqueo del dispositivo mientras tanto
        await _warnOnce();
      }
    }
    if (ok && mounted) setState(() => _locked = false);
  }

  Future<bool> _deviceProtected() async {
    try {
      return await widget.deviceLock.isDeviceSupported();
    } catch (_) {
      return false;
    }
  }

  Future<void> _warnIfUnprotected() async {
    if (!await _deviceProtected()) await _warnOnce();
  }

  Future<void> _warnOnce() async {
    if (await widget.storage.containsKey(key: _lockWarningShownKey)) return;
    await widget.storage.write(key: _lockWarningShownKey, value: '1');
    _messenger.currentState?.showSnackBar(const SnackBar(content: Text(lockWarning), duration: Duration(seconds: 8)));
  }

  Future<void> _signOut() async {
    try {
      await widget.auth.signOut();
    } catch (_) {
      // Sin red el servidor no se entera, pero la sesión local se borra igual.
    } finally {
      await widget.sessionStore.removePersistedSession();
    }
    if (mounted) setState(() => _locked = false);
  }

  @override
  Widget build(BuildContext context) {
    final session = widget.auth.currentSession;
    final Widget home;
    if (session == null) {
      home = AuthScreen(auth: widget.auth, openUrl: widget.openUrl);
    } else if (_locked) {
      home = LockScreen(onUnlock: _unlock);
    } else {
      home = HomeScreen(
        key: ValueKey(session.user.id),
        client: widget.client,
        token: session.accessToken,
        onSignOut: _signOut,
      );
    }
    return MaterialApp(title: 'Finanzas Sin Filtro', scaffoldMessengerKey: _messenger, home: home);
  }
}

class LockScreen extends StatelessWidget {
  const LockScreen({super.key, required this.onUnlock});

  final VoidCallback onUnlock;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.lock_outline, size: 48),
            const SizedBox(height: 16),
            FilledButton(onPressed: onUnlock, child: const Text('Desbloquear')),
          ],
        ),
      ),
    );
  }
}
