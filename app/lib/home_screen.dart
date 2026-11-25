import 'dart:async';

import 'package:app_links/app_links.dart';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import 'api.dart';
import 'auth_screen.dart' show openInBrowser;
import 'budget_form.dart';
import 'money.dart';
import 'movements.dart';
import 'pockets_screen.dart';

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

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  late final api = Api(widget.client, widget.token);
  Map<String, dynamic>? _gps, _me;
  List<Map<String, dynamic>> _movements = const [];
  bool _loading = true, _failed = false, _connecting = false;
  StreamSubscription<Uri>? _linkSub;
  StreamSubscription<void>? _changeSub;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _linkSub = (widget.links ?? AppLinks().uriLinkStream).listen(_onLink);
    _changeSub = widget.changes?.call().listen((_) => _load());
    _load();
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _linkSub?.cancel();
    _changeSub?.cancel();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) _load(); // al volver a la app (y de Google)
  }

  /// Vuelta del backend tras conectar Gmail: co.finanzassinfiltro.fsfapp://gmail-connected?status=ok|error
  void _onLink(Uri uri) {
    if (uri.host != 'gmail-connected' || !mounted) return;
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

  void _openPockets() => Navigator.of(
    context,
  ).push(MaterialPageRoute<void>(builder: (_) => PocketsScreen(api: api, onChanged: _load)));

  void _openMovement(Map<String, dynamic> m) => showModalBottomSheet<void>(
    context: context,
    isScrollControlled: true,
    builder: (_) => MovementSheet(api: api, movement: m, now: widget.now(), onChanged: _load),
  );

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        actions: [
          IconButton(tooltip: 'Bolsillos', icon: const Icon(Icons.savings_outlined), onPressed: _openPockets),
          PopupMenuButton<String>(
            tooltip: 'Más opciones',
            onSelected: (value) => switch (value) {
              'budget' => _openBudget(),
              'gmail' => _connectGmail(),
              _ => widget.onSignOut(),
            },
            itemBuilder: (_) => [
              if (_gps?['estado'] == 'ok') const PopupMenuItem(value: 'budget', child: Text('Presupuesto')),
              if (_me != null && !_gmailActive) const PopupMenuItem(value: 'gmail', child: Text('Conectar correo')),
              const PopupMenuItem(value: 'signout', child: Text('Cerrar sesión')),
            ],
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(padding: const EdgeInsets.fromLTRB(24, 8, 24, 24), children: _body(context)),
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
      Text('Últimos movimientos', style: Theme.of(context).textTheme.titleMedium),
      const SizedBox(height: 8),
      if (_movements.isEmpty) ..._empty(context),
      for (final m in _movements) MovementCard(movement: m, now: widget.now(), onTap: () => _openMovement(m)),
    ];
  }

  List<Widget> _empty(BuildContext context) => [
    const SizedBox(height: 24),
    Text(emptyText, textAlign: TextAlign.center, style: Theme.of(context).textTheme.titleMedium),
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
    final text = Theme.of(context).textTheme;
    final today = g['disponible_hoy'] as String, free = g['saldo_libre'] as String;
    final excess = g['exceso'] as String, review = g['en_revision'] as String;
    final days = g['dias_restantes'] as int;
    final tomorrow = g['diario_desde_manana'] as String?, plan = g['diario_plan'] as String?;
    return [
      const SizedBox(height: 24),
      Text(
        isNegativeAmount(today) ? 'Hoy' : 'Hoy puedes gastar',
        textAlign: TextAlign.center,
        style: text.titleLarge,
      ),
      FittedBox(
        fit: BoxFit.scaleDown,
        child: Text(formatCop(today), key: const Key('disponible_hoy'), style: text.displayLarge),
      ),
      const SizedBox(height: 16),
      if (isNegativeAmount(free))
        Text(
          'Este mes vas ${formatCop(absolute(free))} por encima de lo planeado. '
          'Tu diario queda en ${formatCop('0')} hasta el próximo mes.',
          textAlign: TextAlign.center,
        )
      else ...[
        if (isPositiveAmount(excess)) Text('Hoy fuiste ${formatCop(excess)} más allá de tu diario.', textAlign: TextAlign.center),
        // Efecto GPS: solo cuando un gasto fuera de plan baja el diario de los días siguientes.
        if (isPositiveAmount(excess) && tomorrow != null && plan != null && cents(tomorrow) < cents(plan))
          Text(
            'Tu diario de mañana baja de ${formatCop(plan)} a ${formatCop(tomorrow)}.',
            key: const Key('gps'),
            textAlign: TextAlign.center,
          ),
      ],
      const SizedBox(height: 8),
      Text('Esta semana ${formatCop(g['disponible_semana'] as String)}', textAlign: TextAlign.center),
      Text(
        'Libre este mes ${formatCop(free)} · ${days == 1 ? 'último día' : '$days días'}',
        textAlign: TextAlign.center,
      ),
      if (isPositiveAmount(review)) Text('Incluye ${formatCop(review)} por confirmar', textAlign: TextAlign.center),
    ];
  }
}
