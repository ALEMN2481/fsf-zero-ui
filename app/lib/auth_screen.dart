import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';
import 'package:url_launcher/url_launcher.dart';

import 'theme.dart';

/// Enlace al que vuelve la app tras confirmar el correo o iniciar sesión con Google.
const authRedirect = 'co.finanzassinfiltro.fsfapp://login-callback';

final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

/// Abre la página de Google fuera de la app (Google no permite el inicio de sesión en un WebView).
Future<bool> openInBrowser(Uri url) => launchUrl(url, mode: LaunchMode.externalApplication);

/// Registro e inicio de sesión en un solo formulario de 2 campos (RQN 05).
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, required this.auth, this.openUrl = openInBrowser});

  final GoTrueClient auth;
  final Future<bool> Function(Uri url) openUrl;

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _form = GlobalKey<FormState>();
  final _email = TextEditingController();
  final _password = TextEditingController();
  bool _register = false;
  bool _obscure = true;
  bool _busy = false;
  String? _message;

  @override
  void dispose() {
    _email.dispose();
    _password.dispose();
    super.dispose();
  }

  Future<void> _submit() async {
    if (!_form.currentState!.validate()) return;
    await _run(() async {
      final email = _email.text.trim();
      if (!_register) {
        await widget.auth.signInWithPassword(email: email, password: _password.text);
        return null;
      }
      await widget.auth.signUp(email: email, password: _password.text, emailRedirectTo: authRedirect);
      return 'Revisa tu correo para confirmar la cuenta';
    });
  }

  /// Google: la sesión llega luego por el enlace de vuelta (supabase_flutter la recoge).
  Future<void> _google() => _run(() async {
    final res = await widget.auth.getOAuthSignInUrl(provider: OAuthProvider.google, redirectTo: authRedirect);
    return await widget.openUrl(Uri.parse(res.url)) ? null : 'No se pudo abrir el navegador';
  });

  /// Ejecuta [action] con el formulario ocupado y muestra su mensaje o el del error.
  Future<void> _run(Future<String?> Function() action) async {
    setState(() {
      _busy = true;
      _message = null;
    });
    String? message;
    try {
      message = await action();
    } on AuthException catch (e) {
      message = authErrorMessage(e);
    } catch (_) {
      message = 'No hay conexión. Intenta de nuevo.';
    }
    if (!mounted) return;
    setState(() {
      _busy = false;
      _message = message;
    });
  }

  @override
  Widget build(BuildContext context) {
    const label = TextStyle(fontWeight: FontWeight.w600, fontSize: 15, color: Fsf.textoSecundario);
    return Scaffold(
      body: SafeArea(
        child: SingleChildScrollView(
          padding: const EdgeInsets.all(Fsf.margen),
          child: Form(
            key: _form,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                const SizedBox(height: 16),
                const Align(alignment: Alignment.centerLeft, child: AppLogo(size: 88)),
                const SizedBox(height: 16),
                const Text('Finanzas Sin Filtro', style: TextStyle(fontWeight: FontWeight.w700, fontSize: 32)),
                const SizedBox(height: 4),
                const Text(
                  'Tus finanzas al día, sin enredos',
                  style: TextStyle(fontWeight: FontWeight.w500, fontSize: 16, height: 1.5, color: Fsf.textoSecundario),
                ),
                const SizedBox(height: 24),
                const Text('Correo electrónico', style: label),
                const SizedBox(height: 8),
                TextFormField(
                  key: const Key('email'),
                  controller: _email,
                  decoration: const InputDecoration(hintText: 'ejemplo@correo.com'),
                  keyboardType: TextInputType.emailAddress,
                  autofillHints: const [AutofillHints.email],
                  validator: (v) => _emailPattern.hasMatch(v?.trim() ?? '') ? null : 'Escribe un correo válido',
                ),
                const SizedBox(height: 16),
                const Text('Contraseña', style: label),
                const SizedBox(height: 8),
                TextFormField(
                  key: const Key('password'),
                  controller: _password,
                  obscureText: _obscure,
                  decoration: InputDecoration(
                    hintText: 'Tu contraseña',
                    suffixIcon: IconButton(
                      tooltip: _obscure ? 'Mostrar contraseña' : 'Ocultar contraseña',
                      icon: Icon(_obscure ? Icons.visibility_outlined : Icons.visibility_off_outlined),
                      onPressed: () => setState(() => _obscure = !_obscure),
                    ),
                  ),
                  autofillHints: [_register ? AutofillHints.newPassword : AutofillHints.password],
                  validator: (v) => (v ?? '').length >= 8 ? null : 'Mínimo 8 caracteres',
                ),
                const SizedBox(height: 24),
                FilledButton(onPressed: _busy ? null : _submit, child: Text(_register ? 'Crear cuenta' : 'Entrar')),
                if (_message != null)
                  Padding(
                    padding: const EdgeInsets.only(top: 12),
                    child: Text(_message!, textAlign: TextAlign.center),
                  ),
                const SizedBox(height: 16),
                const Row(
                  children: [
                    Expanded(child: Divider(color: Fsf.borde)),
                    Flexible(
                      child: Padding(
                        padding: EdgeInsets.symmetric(horizontal: 12),
                        child: Text('o continúa con', style: Fsf.ayuda, textAlign: TextAlign.center),
                      ),
                    ),
                    Expanded(child: Divider(color: Fsf.borde)),
                  ],
                ),
                const SizedBox(height: 16),
                OutlinedButton(onPressed: _busy ? null : _google, child: const Text('Continuar con Google')),
                const SizedBox(height: 16),
                Container(
                  padding: const EdgeInsets.all(16),
                  decoration: const BoxDecoration(
                    color: Fsf.superficie,
                    borderRadius: BorderRadius.all(Radius.circular(20)),
                  ),
                  child: const Row(
                    children: [
                      Icon(Icons.bolt),
                      SizedBox(width: 12),
                      Expanded(
                        child: Text(
                          'Lectura automática de facturas y notificaciones, sin registros manuales',
                          style: TextStyle(color: Fsf.textoSecundarioEnSuperficie),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                TextButton(
                  onPressed: _busy
                      ? null
                      : () => setState(() {
                          _register = !_register;
                          _message = null;
                        }),
                  child: Text(_register ? '¿Ya tienes cuenta? Entrar' : '¿No tienes cuenta? Crear una'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

/// Logo oficial (docs/design/logo.png), sobre su fondo blanco.
class AppLogo extends StatelessWidget {
  const AppLogo({super.key, this.size = 96});

  final double size;

  @override
  Widget build(BuildContext context) =>
      Image.asset('assets/images/logo.png', width: size, height: size, semanticLabel: 'Finanzas Sin Filtro');
}

String authErrorMessage(AuthException e) => switch (e.code) {
  'email_not_confirmed' => 'Confirma tu correo antes de iniciar sesión',
  'invalid_credentials' => 'Correo o contraseña incorrectos',
  'user_already_exists' => 'Ese correo ya tiene una cuenta',
  'weak_password' => 'La contraseña debe tener al menos 8 caracteres',
  'over_email_send_rate_limit' || 'over_request_rate_limit' => 'Demasiados intentos. Espera unos minutos.',
  _ => 'No se pudo completar. Intenta de nuevo.',
};
