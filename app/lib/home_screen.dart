import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'api.dart';
import 'auth_screen.dart' show openInBrowser;
import 'budget_form.dart';
import 'coach_screen.dart';
import 'data_sources_screen.dart';
import 'money.dart';
import 'movements.dart';
import 'pockets_screen.dart';
import 'push.dart';
import 'theme.dart';
import 'tutorial.dart';

const emptyText = 'A la espera de tu primera captura automática';
const loadError = 'No pudimos cargar tus datos';

/// Pantalla principal «Disponible diario» (Paso 12, CU-03): una cifra grande y los últimos
/// movimientos en tarjetas simples. Todas las cifras vienen calculadas del backend (D12).
class HomeScreen extends StatefulWidget {
  const HomeScreen({
    super.key,
    required this.client,
    required this.token,
    required this.onSignOut,
    this.openUrl = openInBrowser,
    this.links,
    this.changes,
    this.now = DateTime.now,
    this.showTutorial = false,
    this.onTutorialDone,
    this.push,
    this.askPush = false,
    this.onPushAsked,
  });

  final http.Client client;
  final String token;
  final VoidCallback onSignOut;
  final Future<bool> Function(Uri url) openUrl;

  /// Enlaces que abren la app (por defecto, los del sistema); los tests pasan los suyos.
  final Stream<Uri>? links;

  /// Aviso de que cambió un movimiento del usuario (Supabase Realtime); solo dispara el refresco.
  final Stream<void> Function()? changes;
  final DateTime Function() now;

  /// Primer uso: el tutorial «Primer vistazo» se muestra encima cuando ya hay cifras (D14).
  final bool showTutorial;
  final VoidCallback? onTutorialDone;

  /// Avisos push (Paso 14); null en los tests que no los usan.
  final Push? push;

  /// Primer uso: tras el tutorial se explica para qué son los avisos y se pide el permiso una vez.
  final bool askPush;
  final VoidCallback? onPushAsked;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  // Getter, no late final: Supabase renueva el token cada hora y la principal se reconstruye con el
  // nuevo; con el cliente guardado, a la hora todo daba 401 (visto al tocar un aviso, Paso 14).
  Api get api => Api(widget.client, widget.token);
  Map<String, dynamic>? _gps, _me;
  List<Map<String, dynamic>> _movements = const [];
  bool _loading = true, _failed = false, _connecting = false;
  StreamSubscription<Uri>? _linkSub;
  StreamSubscription<void>? _changeSub;
  final _pushSubs = <StreamSubscription<Object?>>[];
  String? _pushToken;
  bool _askingPush = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _linkSub = (widget.links ?? AppLinks().uriLinkStream).listen(_onLink);
    _changeSub = widget.changes?.call().listen((_) => _load());
    _load();
    _startPush();
  }

  /// Registra el dispositivo en el backend y, con la app abierta, refresca y lo dice brevemente.
  Future<void> _startPush() async {
    final push = widget.push;
    if (push == null) return;
    _pushSubs
      ..add(push.tokenRefresh.listen(_registerDevice))
      ..add(
        push.foreground.listen((data) {
          _load();
          if (mounted && data['title'] != null) _say(data['title']!);
        }),
      );
    try {
      final token = await push.token();
      if (token != null) await _registerDevice(token);
    } catch (_) {
      // Sin Google Play o sin red: la app funciona igual, sin avisos.
    }
  }

  Future<void> _registerDevice(String token) async {
    _pushToken = token;
    try {
      await api.post('/devices', {'token': token});
    } catch (_) {}
  }

  /// Al cerrar sesión este teléfono deja de recibir los avisos de la cuenta.
  Future<void> _signOut() async {
    final token = _pushToken;
    if (token != null) {
      try {
        await api.delete('/devices', {'token': token});
        await widget.push?.deleteToken();
      } catch (_) {}
    }
    widget.onSignOut();
  }

  @override
  void didUpdateWidget(HomeScreen old) {
    super.didUpdateWidget(old);
    if (old.showTutorial && !widget.showTutorial) _maybeAskPush();
  }

  /// Una sola vez, con contexto: después del tutorial y con las cifras ya en pantalla.
  Future<void> _maybeAskPush() async {
    final push = widget.push;
    if (push == null || !widget.askPush || widget.showTutorial || _askingPush || _gps?['estado'] != 'ok') return;
    _askingPush = true;
    if (await push.enabled()) {
      widget.onPushAsked?.call();
      return;
    }
    if (!mounted) return;
    final accept = await showModalBottomSheet<bool>(context: context, builder: (_) => const PushPrompt());
    widget.onPushAsked?.call();
    if (accept == true) await push.requestPermission();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _linkSub?.cancel();
    _changeSub?.cancel();
    for (final s in _pushSubs) {
      s.cancel();
    }
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _load(); // al volver a la app (y de Google)
  }

  /// Vuelta del backend tras conectar Gmail: co.finanzassinfiltro.fsfapp://gmail-connected?status=ok|error
  void _onLink(Uri uri) {
    if (!mounted) return;
    // Al tocar un aviso push (Paso 14).
    if (uri.host == 'movimiento' && uri.pathSegments.isNotEmpty) {
      _openMovementById(uri.pathSegments.first);
      return;
    }
    if (uri.host == 'fuentes') {
      _openSources();
      return;
    }
    if (uri.host != 'gmail-connected') return;
    _load();
    if (uri.queryParameters['status'] != 'ok') _say('No se pudo conectar Gmail, inténtalo de nuevo');
  }

  void _say(String text) => ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));

  Future<void> _load() async {
    try {
      final results = await Future.wait([api.get('/gps'), api.get('/movements'), api.get('/me')]);
      if (!mounted) return;
      setState(() {
        _gps = results[0] as Map<String, dynamic>;
        _movements = (results[1] as List).cast<Map<String, dynamic>>();
        _me = results[2] as Map<String, dynamic>;
        _failed = _gps!['estado'] == null;
        _loading = false;
      });
      _maybeAskPush();
    } catch (_) {
      if (mounted) {
        setState(() {
          _failed = true;
          _loading = false;
        });
      }
    }
  }

  Future<void> _connectGmail() async {
    setState(() => _connecting = true);
    try {
      final res = await api.post('/gmail/connect') as Map<String, dynamic>;
      if (!await widget.openUrl(Uri.parse(res['url'] as String))) throw StateError('sin navegador');
    } catch (_) {
      if (mounted) _say('No se pudo iniciar la conexión con Gmail');
    } finally {
      if (mounted) setState(() => _connecting = false);
    }
  }

  bool get _gmailActive => _me?['gmail_status'] == 'active';

  void _openBudget() {
    Navigator.of(context).push(
      MaterialPageRoute<void>(
        builder: (context) => Scaffold(
          appBar: AppBar(title: const Text('Presupuesto')),
          body: ListView(
            padding: const EdgeInsets.all(24),
            children: [
              BudgetForm(
                api: api,
                current: (_gps?['periodo'] as Map?)?['presupuesto'] as String?,
                onSaved: () {
                  Navigator.of(context).pop();
                  _load();
                },
              ),
            ],
          ),
        ),
      ),
    );
  }

  void _openSources() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => DataSourcesScreen(
        status: () async => ((await api.get('/me')) as Map<String, dynamic>)['gmail_status'] as String?,
        connect: _connectGmail,
        push: widget.push,
      ),
    ),
  );

  void _openPockets() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => PocketsScreen(api: api, onChanged: _load),
    ),
  );

  void _openCoach() => Navigator.of(context).push(
    MaterialPageRoute<void>(
      builder: (_) => CoachScreen(api: api, now: widget.now),
    ),
  );

  Future<void> _openMovementById(String id) async {
    try {
      final m = await api.get('/transactions/$id') as Map<String, dynamic>;
      if (mounted) _openMovement(m);
    } catch (_) {
      if (mounted) _say('No encontramos ese movimiento');
    }
  }

  void _openMovement(Map<String, dynamic> m) => showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => MovementSheet(api: api, movement: m, now: widget.now(), onChanged: _load),
  );

  @override
  Widget build(BuildContext context) {
    final screen = _screen(context);
    if (!widget.showTutorial || _gps?['estado'] != 'ok') return screen;
    return Stack(
      children: [
        screen,
        Positioned.fill(
          child: TutorialOverlay(gps: _gps!, onDone: widget.onTutorialDone ?? () {}),
        ),
      ],
    );
  }

  Widget _screen(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(tooltip: 'Bolsillos', icon: const Icon(Icons.savings_outlined), onPressed: _openPockets),
          PopupMenuButton<String>(
            tooltip: 'Más opciones',
            onSelected: (value) => switch (value) {
              'budget' => _openBudget(),
              'sources' => _openSources(),
              _ => _signOut(),
            },
            itemBuilder: (_) => [
              if (_gps?['estado'] == 'ok') const PopupMenuItem(value: 'budget', child: Text('Presupuesto')),
              const PopupMenuItem(value: 'sources', child: Text('Fuentes de datos')),
              const PopupMenuItem(value: 'signout', child: Text('Cerrar sesión')),
            ],
          ),
        ],
      ),
      floatingActionButton: _loading || _failed
          ? null
          : FloatingActionButton(
              tooltip: 'Abrir el Coach',
              shape: const CircleBorder(),
              onPressed: _openCoach,
              child: const Icon(Icons.auto_awesome),
            ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          // Abajo, espacio para que el botón del Coach no tape el último movimiento.
          padding: const EdgeInsets.fromLTRB(Fsf.margen, 0, Fsf.margen, 96),
          children: _body(context),
        ),
      ),
    );
  }

  List<Widget> _body(BuildContext context) {
    if (_loading) return const [Center(child: CircularProgressIndicator())];
    if (_failed) {
      return [
        const Text(loadError),
        const SizedBox(height: 8),
        FilledButton(onPressed: _load, child: const Text('Reintentar')),
      ];
    }
    final gps = _gps!;
    if (gps['estado'] != 'ok') return [BudgetForm(api: api, onSaved: _load)];
    return [
      ...DailySummary.lines(context, gps),
      const SizedBox(height: 32),
      const Text('Últimos movimientos', style: Fsf.tituloSeccion),
      const SizedBox(height: 12),
      if (_movements.isEmpty) ..._empty(context),
      for (final m in _movements) MovementCard(movement: m, now: widget.now(), onTap: () => _openMovement(m)),
    ];
  }

  List<Widget> _empty(BuildContext context) => [
    const SizedBox(height: 24),
    const Text(emptyText, textAlign: TextAlign.center, style: Fsf.tarjeta),
    if (_me != null && _me!['gmail_status'] == 'needs_reconnect') ...[
      const SizedBox(height: 8),
      const Text('La conexión con Gmail se cayó', textAlign: TextAlign.center),
    ],
    if (_me != null && !_gmailActive) ...[
      const SizedBox(height: 16),
      FilledButton(onPressed: _connecting ? null : _connectGmail, child: const Text('Conectar correo')),
    ],
  ];
}

/// La cifra grande y, debajo, pocas líneas. Textos neutrales: la app no juzga.
class DailySummary {
  static List<Widget> lines(BuildContext context, Map<String, dynamic> g) {
    final today = g['disponible_hoy'] as String, free = g['saldo_libre'] as String;
    final excess = g['exceso'] as String, review = g['en_revision'] as String;
    final days = g['dias_restantes'] as int;
    final tomorrow = g['diario_desde_manana'] as String?, plan = g['diario_plan'] as String?;
    const line = TextStyle(fontSize: 15, color: Fsf.textoSecundario);
    return [
      const SizedBox(height: 16),
      Text(isNegativeAmount(today) ? 'HOY' : 'HOY PUEDES GASTAR', style: Fsf.etiqueta),
      const SizedBox(height: 4),
      // Unbounded es muy ancha: con el texto al 200 % la cifra se reduce, no desborda.
      FittedBox(
        fit: BoxFit.scaleDown,
        alignment: Alignment.centerLeft,
        child: Text(formatCop(today), key: const Key('disponible_hoy'), style: Fsf.cifra),
      ),
      const SizedBox(height: 12),
      if (isNegativeAmount(free))
        Text(
          'Este mes vas ${formatCop(absolute(free))} por encima de lo planeado. '
          'Tu diario queda en ${formatCop('0')} hasta el próximo mes.',
          style: Fsf.tarjeta.copyWith(fontWeight: FontWeight.w500),
        )
      else ...[
        if (isPositiveAmount(excess))
          Text(
            'Hoy fuiste ${formatCop(excess)} más allá de tu diario.',
            style: Fsf.tarjeta.copyWith(fontWeight: FontWeight.w500),
          ),
        // Efecto GPS: solo cuando un gasto fuera de plan baja el diario de los días siguientes.
        if (isPositiveAmount(excess) && tomorrow != null && plan != null && cents(tomorrow) < cents(plan))
          Text(
            'Tu diario de mañana baja de ${formatCop(plan)} a ${formatCop(tomorrow)}.',
            key: const Key('gps'),
            style: Fsf.tarjeta.copyWith(fontWeight: FontWeight.w500),
          ),
      ],
      const SizedBox(height: 4),
      Text('Esta semana ${formatCop(g['disponible_semana'] as String)}', style: line),
      Text('Libre este mes ${formatCop(free)} · ${days == 1 ? 'último día' : '$days días'}', style: line),
      if (isPositiveAmount(review)) Text('Incluye ${formatCop(review)} por confirmar', style: line),
      if (g['reservado'] != null) ...[const SizedBox(height: 16), ReservedCard(amount: g['reservado'] as String)],
    ];
  }
}

/// «Reservado»: lo apartado en todos los bolsillos (cifra del backend, D14).
class ReservedCard extends StatelessWidget {
  const ReservedCard({super.key, required this.amount});

  final String amount;

  @override
  Widget build(BuildContext context) => Container(
    padding: const EdgeInsets.all(16),
    decoration: const BoxDecoration(color: Fsf.superficie, borderRadius: BorderRadius.all(Radius.circular(20))),
    child: Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Row(
          children: [
            Icon(Icons.shield_outlined, size: 18, color: Fsf.textoSecundarioEnSuperficie),
            SizedBox(width: 8),
            Text('Reservado', style: TextStyle(fontSize: 14, color: Fsf.textoSecundarioEnSuperficie)),
          ],
        ),
        const SizedBox(height: 4),
        FittedBox(
          fit: BoxFit.scaleDown,
          alignment: Alignment.centerLeft,
          child: Text(formatCop(amount), key: const Key('reservado'), style: Fsf.montoTarjeta.copyWith(fontSize: 20)),
        ),
      ],
    ),
  );
}

/// Por qué pedimos el permiso de avisos, antes del diálogo del sistema (Android 13+).
class PushPrompt extends StatelessWidget {
  const PushPrompt({super.key});

  @override
  Widget build(BuildContext context) => SafeArea(
    child: SingleChildScrollView(
      padding: const EdgeInsets.fromLTRB(Fsf.margen, 0, Fsf.margen, Fsf.margen),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('¿Te avisamos?', style: Fsf.tituloSeccion),
          const SizedBox(height: 12),
          const Text(
            'Te avisamos cuando registremos un gasto o haya algo por confirmar. '
            'En la pantalla de bloqueo no se ven cifras.',
            style: TextStyle(fontSize: 16, height: 1.5),
          ),
          const SizedBox(height: 24),
          FilledButton(onPressed: () => Navigator.of(context).pop(true), child: const Text('Activar avisos')),
          const SizedBox(height: 8),
          TextButton(onPressed: () => Navigator.of(context).pop(false), child: const Text('Ahora no')),
        ],
      ),
    ),
  );
}
