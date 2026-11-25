import 'package:flutter/material.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

/// Enlace al que vuelve la app tras confirmar el correo (y, en la Parte B, tras Google).
const authRedirect = 'co.finanzassinfiltro.fsfapp://login-callback';

final _emailPattern = RegExp(r'^[^@\s]+@[^@\s]+\.[^@\s]+$');

/// Registro e inicio de sesión en un solo formulario de 2 campos (RQN 05).
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key, required this.auth});

  final GoTrueClient auth;

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
    setState(() {
      _busy = true;
      _message = null;
    });
    String? message;
    try {
      final email = _email.text.trim();
      if (_register) {
        await widget.auth.signUp(email: email, password: _password.text, emailRedirectTo: authRedirect);
        message = 'Revisa tu correo para confirmar la cuenta';
      } else {
        await widget.auth.signInWithPassword(email: email, password: _password.text);
      }
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
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: Form(
              key: _form,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  Text(
                    'Finanzas Sin Filtro',
                    textAlign: TextAlign.center,
                    style: Theme.of(context).textTheme.headlineSmall,
                  ),
                  const SizedBox(height: 24),
                  TextFormField(
                    controller: _email,
                    decoration: const InputDecoration(labelText: 'Correo'),
                    keyboardType: TextInputType.emailAddress,
                    autofillHints: const [AutofillHints.email],
                    validator: (v) => _emailPattern.hasMatch(v?.trim() ?? '') ? null : 'Escribe un correo válido',
                  ),
                  const SizedBox(height: 12),
                  TextFormField(
                    controller: _password,
                    obscureText: _obscure,
                    decoration: InputDecoration(
                      labelText: 'Contraseña',
                      suffixIcon: IconButton(
                        tooltip: _obscure ? 'Mostrar contraseña' : 'Ocultar contraseña',
                        icon: Icon(_obscure ? Icons.visibility : Icons.visibility_off),
                        onPressed: () => setState(() => _obscure = !_obscure),
                      ),
                    ),
                    autofillHints: [_register ? AutofillHints.newPassword : AutofillHints.password],
                    validator: (v) => (v ?? '').length >= 8 ? null : 'Mínimo 8 caracteres',
                  ),
                  const SizedBox(height: 24),
                  FilledButton(onPressed: _busy ? null : _submit, child: Text(_register ? 'Crear cuenta' : 'Entrar')),
                  TextButton(
                    onPressed: _busy
                        ? null
                        : () => setState(() {
                            _register = !_register;
                            _message = null;
                          }),
                    child: Text(_register ? '¿Ya tienes cuenta? Entrar' : '¿No tienes cuenta? Crear una'),
                  ),
                  if (_message != null)
                    Padding(
                      padding: const EdgeInsets.only(top: 12),
                      child: Text(_message!, textAlign: TextAlign.center),
                    ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }
}

String authErrorMessage(AuthException e) => switch (e.code) {
  'email_not_confirmed' => 'Confirma tu correo antes de iniciar sesión',
  'invalid_credentials' => 'Correo o contraseña incorrectos',
  'user_already_exists' => 'Ese correo ya tiene una cuenta',
  'weak_password' => 'La contraseña debe tener al menos 8 caracteres',
  'over_email_send_rate_limit' || 'over_request_rate_limit' => 'Demasiados intentos. Espera unos minutos.',
  _ => 'No se pudo completar. Intenta de nuevo.',
};
