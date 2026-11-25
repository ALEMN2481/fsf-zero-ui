import 'package:flutter/material.dart';

import 'api.dart';
import 'budget_form.dart' show amountHint;
import 'money.dart';

/// Bolsillos (CU-05): saldo y, si tiene meta, una barra de progreso plana (no es un gráfico).
class PocketsScreen extends StatefulWidget {
  const PocketsScreen({super.key, required this.api, required this.onChanged});

  final Api api;

  /// Apartar o retirar cambia el saldo libre: la pantalla principal se refresca.
  final VoidCallback onChanged;

  @override
  State<PocketsScreen> createState() => _PocketsScreenState();
}

class _PocketsScreenState extends State<PocketsScreen> {
  late Future<List<Map<String, dynamic>>> _pockets = _load();

  Future<List<Map<String, dynamic>>> _load() async =>
      ((await widget.api.get('/pockets')) as List).cast<Map<String, dynamic>>();

  void _refresh() {
    setState(() {
      _pockets = _load();
    });
    widget.onChanged();
  }

  Future<void> _open(Widget sheet) async {
    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      builder: (context) =>
          Padding(padding: EdgeInsets.only(bottom: MediaQuery.viewInsetsOf(context).bottom), child: sheet),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Bolsillos')),
      floatingActionButton: FloatingActionButton(
        tooltip: 'Crear bolsillo',
        onPressed: () => _open(CreatePocketSheet(api: widget.api, onChanged: _refresh)),
        child: const Icon(Icons.add),
      ),
      body: FutureBuilder<List<Map<String, dynamic>>>(
        future: _pockets,
        builder: (context, snap) {
          if (snap.hasError) return const Center(child: Text('No pudimos cargar tus bolsillos'));
          if (!snap.hasData) return const Center(child: CircularProgressIndicator());
          final pockets = snap.data!;
          if (pockets.isEmpty) {
            return const Padding(
              padding: EdgeInsets.all(24),
              child: Text('Aparta dinero para una meta: toca + para crear tu primer bolsillo.'),
            );
          }
          return ListView(
            padding: const EdgeInsets.fromLTRB(16, 16, 16, 96),
            children: [
              for (final p in pockets)
                PocketCard(
                  pocket: p,
                  onMove: (sign) => _open(
                    MoveSheet(api: widget.api, pocketId: p['id'] as String, withdraw: sign < 0, onChanged: _refresh),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }
}

class PocketCard extends StatelessWidget {
  const PocketCard({super.key, required this.pocket, required this.onMove});

  final Map<String, dynamic> pocket;
  final void Function(int sign) onMove;

  @override
  Widget build(BuildContext context) {
    final p = pocket, balance = p['saldo'] as String, target = p['target_amount'] as String?;
    final text = Theme.of(context).textTheme;
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(p['name'] as String, style: text.titleMedium),
            Text(formatCop(balance), style: text.headlineSmall),
            if (target != null) ...[
              const SizedBox(height: 8),
              LinearProgressIndicator(
                // Solo la proporción visual de la barra; las cifras se muestran como texto exacto.
                value: (cents(balance) * BigInt.from(1000) ~/ cents(target)).toInt().clamp(0, 1000) / 1000,
                semanticsLabel: '${formatCop(balance)} de ${formatCop(target)}',
              ),
              Text('de ${formatCop(target)}'),
            ],
            Wrap(
              spacing: 8,
              children: [
                TextButton(onPressed: () => onMove(1), child: const Text('Apartar')),
                TextButton(onPressed: () => onMove(-1), child: const Text('Retirar')),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

/// Mensaje y monto sugerido cuando el backend responde 409 con el máximo posible (CU-05 A1).
({String message, String? maximum}) moveError(Object error, {required bool withdraw}) {
  if (error is ApiError && error.status == 409) {
    if (error.field('motivo') == 'sin_presupuesto') {
      return (message: 'Primero define tu presupuesto del mes', maximum: null);
    }
    final max = error.field('maximo');
    if (max != null && isPositiveAmount(max)) {
      return (
        message: withdraw ? 'Puedes retirar hasta ${formatCop(max)}' : 'Puedes apartar hasta ${formatCop(max)}',
        maximum: max,
      );
    }
    return (message: withdraw ? 'Este bolsillo está vacío' : 'Hoy no tienes saldo libre para apartar', maximum: null);
  }
  return (message: 'No se pudo guardar, inténtalo de nuevo', maximum: null);
}

/// Apartar o retirar: un campo.
class MoveSheet extends StatefulWidget {
  const MoveSheet({super.key, required this.api, required this.pocketId, required this.withdraw, required this.onChanged});

  final Api api;
  final String pocketId;
  final bool withdraw;
  final VoidCallback onChanged;

  @override
  State<MoveSheet> createState() => _MoveSheetState();
}

class _MoveSheetState extends State<MoveSheet> {
  final _amount = TextEditingController();
  String? _error, _maximum;
  bool _busy = false;

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _move(String? amount) async {
    if (amount == null) {
      setState(() => _error = amountHint);
      return;
    }
    setState(() => _busy = true);
    try {
      await widget.api.post('/pockets/${widget.pocketId}/movements', {
        'amount': widget.withdraw ? '-$amount' : amount,
      });
      widget.onChanged();
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      final err = moveError(e, withdraw: widget.withdraw);
      if (mounted) {
        setState(() {
          _error = err.message;
          _maximum = err.maximum;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final verb = widget.withdraw ? 'Retirar' : 'Apartar';
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            TextField(
              controller: _amount,
              autofocus: true,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: 'Monto a ${verb.toLowerCase()}', prefixText: '\$ ', errorText: _error),
            ),
            const SizedBox(height: 16),
            if (_maximum != null)
              FilledButton(
                onPressed: _busy ? null : () => _move(_maximum),
                child: Text('$verb ${formatCop(_maximum!)}'),
              ),
            FilledButton(onPressed: _busy ? null : () => _move(parseCopInput(_amount.text)), child: Text(verb)),
          ],
        ),
      ),
    );
  }
}

/// Crear bolsillo: nombre y monto a reservar (CU-05); la meta es opcional y va oculta.
class CreatePocketSheet extends StatefulWidget {
  const CreatePocketSheet({super.key, required this.api, required this.onChanged});

  final Api api;
  final VoidCallback onChanged;

  @override
  State<CreatePocketSheet> createState() => _CreatePocketSheetState();
}

class _CreatePocketSheetState extends State<CreatePocketSheet> {
  final _name = TextEditingController(), _amount = TextEditingController(), _target = TextEditingController();
  bool _withTarget = false, _busy = false;
  String? _error, _maximum, _pocketId;

  @override
  void dispose() {
    _name.dispose();
    _amount.dispose();
    _target.dispose();
    super.dispose();
  }

  Future<void> _save({String? amountOverride}) async {
    final name = _name.text.trim();
    final amount = amountOverride ?? (_amount.text.trim().isEmpty ? null : parseCopInput(_amount.text));
    final target = _withTarget && _target.text.trim().isNotEmpty ? parseCopInput(_target.text) : null;
    if (name.isEmpty || (_amount.text.trim().isNotEmpty && amount == null) ||
        (_withTarget && _target.text.trim().isNotEmpty && target == null)) {
      setState(() => _error = name.isEmpty ? 'Ponle un nombre al bolsillo' : amountHint);
      return;
    }
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      // Si el apartado falló antes por sobregiro, el bolsillo ya existe: no se crea dos veces.
      _pocketId ??= ((await widget.api.post('/pockets', {'name': name, 'target_amount': ?target})) as Map)['id'] as String;
      if (amount != null) await widget.api.post('/pockets/$_pocketId/movements', {'amount': amount});
      widget.onChanged();
      if (mounted) Navigator.of(context).pop();
    } catch (e) {
      final err = moveError(e, withdraw: false);
      if (_pocketId != null) widget.onChanged(); // el bolsillo se creó aunque el apartado no
      if (mounted) {
        setState(() {
          _error = err.message;
          _maximum = err.maximum;
        });
      }
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text('Nuevo bolsillo', style: Theme.of(context).textTheme.titleLarge),
            TextField(
              controller: _name,
              enabled: _pocketId == null,
              decoration: const InputDecoration(labelText: 'Nombre, por ejemplo Viaje'),
            ),
            TextField(
              controller: _amount,
              keyboardType: const TextInputType.numberWithOptions(decimal: true),
              decoration: InputDecoration(labelText: 'Monto a reservar', prefixText: '\$ ', errorText: _error),
            ),
            if (_withTarget)
              TextField(
                controller: _target,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'Meta (opcional)', prefixText: '\$ '),
              )
            else if (_pocketId == null)
              TextButton(onPressed: () => setState(() => _withTarget = true), child: const Text('Añadir meta')),
            const SizedBox(height: 16),
            if (_maximum != null)
              FilledButton(
                onPressed: _busy ? null : () => _save(amountOverride: _maximum),
                child: Text('Apartar ${formatCop(_maximum!)}'),
              ),
            FilledButton(onPressed: _busy ? null : _save, child: const Text('Crear')),
          ],
        ),
      ),
    );
  }
}
