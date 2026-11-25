import 'package:flutter/material.dart';

import 'api.dart';
import 'money.dart';

const pendingLabel = 'POR CONFIRMAR';
const _months = ['ene', 'feb', 'mar', 'abr', 'may', 'jun', 'jul', 'ago', 'sep', 'oct', 'nov', 'dic'];

/// Hora de Colombia (UTC−5 todo el año, sin horario de verano) como campos de un DateTime UTC.
DateTime bogota(DateTime t) => t.toUtc().subtract(const Duration(hours: 5));

/// "hoy 07:45", "ayer 18:10" o "21 nov", en hora de Colombia.
String dateLabel(String iso, DateTime now) {
  final t = bogota(DateTime.parse(iso)), today = bogota(now);
  final day = DateTime.utc(t.year, t.month, t.day), current = DateTime.utc(today.year, today.month, today.day);
  final hhmm = '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
  final diff = current.difference(day).inDays;
  if (diff == 0) return 'hoy $hhmm';
  if (diff == 1) return 'ayer $hhmm';
  return '${t.day} ${_months[t.month - 1]}';
}

/// Monto con su signo según el tipo del motor: los que no cuentan en el presupuesto, sin signo.
String signedAmount(Map<String, dynamic> m) {
  final amount = m['monto'] as String;
  return switch (m['tipo']) {
    'gasto' => formatCop('-$amount'),
    'ingreso' || 'devolucion' => '+${formatCop(amount)}',
    _ => formatCop(amount),
  };
}

String? kindNote(Map<String, dynamic> m) => switch (m['tipo']) {
  'efectivo_factura' => 'efectivo, ya contado en el retiro',
  'entre_cuentas' => 'entre tus cuentas',
  'devolucion' => 'devolución',
  _ => null,
};

String title(Map<String, dynamic> m) =>
    (m['comercio'] as String?) ?? (m['direccion'] == 'income' ? 'Ingreso' : 'Transferencia');

class MovementCard extends StatelessWidget {
  const MovementCard({super.key, required this.movement, required this.now, required this.onTap});

  final Map<String, dynamic> movement;
  final DateTime now;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final m = movement, text = Theme.of(context).textTheme;
    final details = [m['categoria'] ?? 'Sin categoría', dateLabel(m['fecha'] as String, now), ?kindNote(m)];
    return Card(
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(title(m), style: text.titleMedium),
              if (m['estado'] == 'pending_review') Text(pendingLabel, style: text.labelLarge),
              Text(details.join(' · ')),
              Text(signedAmount(m), textAlign: TextAlign.end, style: text.titleMedium),
            ],
          ),
        ),
      ),
    );
  }
}

/// Hoja inferior: categoría con un toque y, si está por confirmar, confirmar o descartar.
class MovementSheet extends StatefulWidget {
  const MovementSheet({super.key, required this.api, required this.movement, required this.now, required this.onChanged});

  final Api api;
  final Map<String, dynamic> movement;
  final DateTime now;
  final VoidCallback onChanged;

  @override
  State<MovementSheet> createState() => _MovementSheetState();
}

class _MovementSheetState extends State<MovementSheet> {
  List<Map<String, dynamic>> _categories = const [];
  late String? _selected = widget.movement['categoria_id'] as String?;
  bool _busy = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    widget.api.get('/categories').then((rows) {
      if (mounted) setState(() => _categories = (rows as List).cast<Map<String, dynamic>>());
    }, onError: (_) {});
  }

  Future<void> _run(Future<void> Function() action, {bool close = false}) async {
    setState(() {
      _busy = true;
      _error = null;
    });
    try {
      await action();
      widget.onChanged();
      if (close && mounted) Navigator.of(context).pop();
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo guardar, inténtalo de nuevo');
    } finally {
      if (mounted) setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final m = widget.movement, id = m['id'], text = Theme.of(context).textTheme;
    final pending = m['estado'] == 'pending_review';
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Text(title(m), style: text.titleLarge),
            Text('${signedAmount(m)} · ${dateLabel(m['fecha'] as String, widget.now)}'),
            if (pending) Text('Por confirmar', style: text.labelLarge),
            const SizedBox(height: 16),
            const Text('Categoría'),
            Wrap(
              spacing: 8,
              children: [
                for (final c in _categories)
                  ChoiceChip(
                    label: Text(c['name'] as String),
                    selected: _selected == c['id'],
                    onSelected: _busy
                        ? null
                        : (_) => _run(() async {
                            await widget.api.patch('/transactions/$id/category', {'category_id': c['id']});
                            if (mounted) setState(() => _selected = c['id'] as String);
                          }),
                  ),
              ],
            ),
            if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            if (pending) ...[
              const SizedBox(height: 16),
              FilledButton(
                onPressed: _busy ? null : () => _run(() => widget.api.post('/transactions/$id/confirm'), close: true),
                child: const Text('Confirmar'),
              ),
              OutlinedButton(
                onPressed: _busy ? null : () => _run(() => widget.api.post('/transactions/$id/dismiss'), close: true),
                child: const Text('No es un gasto mío'),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
