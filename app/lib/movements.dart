import 'package:flutter/material.dart';

import 'api.dart';
import 'money.dart';
import 'theme.dart';

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
const _weekdays = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo'];

/// Título del grupo de movimientos de un día (Paso 15B): «Hoy», «Ayer», «Lunes 24» y, si es de
/// otro mes, «Viernes 31 oct». En hora de Colombia.
String dayLabel(String iso, DateTime now) {
  final t = bogota(DateTime.parse(iso)), today = bogota(now);
  final day = DateTime.utc(t.year, t.month, t.day), current = DateTime.utc(today.year, today.month, today.day);
  final diff = current.difference(day).inDays;
  if (diff == 0) return 'Hoy';
  if (diff == 1) return 'Ayer';
  final label = '${_weekdays[t.weekday - 1]} ${t.day}';
  return t.month == today.month && t.year == today.year ? label : '$label ${_months[t.month - 1]}';
}

/// "07:45", en hora de Colombia (dentro de un grupo por día).
String timeLabel(String iso) {
  final t = bogota(DateTime.parse(iso));
  return '${t.hour.toString().padLeft(2, '0')}:${t.minute.toString().padLeft(2, '0')}';
}

/// Icono de cada categoría (sin emojis, D14); las propias del usuario llevan uno genérico.
IconData categoryIcon(String? name) => switch (name) {
  'Alimentos' => Icons.restaurant_outlined,
  'Transporte' => Icons.directions_bus_outlined,
  'Entretenimiento' => Icons.movie_outlined,
  'Salud' => Icons.local_hospital_outlined,
  'Servicios' => Icons.receipt_long_outlined,
  'Ingresos' => Icons.payments_outlined,
  'Otros' => Icons.category_outlined,
  _ => Icons.label_outline,
};

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
    (m['comercio'] as String?) ??
    switch ((m['direccion'], m['medio'])) {
      ('income', _) => 'Ingreso',
      (_, 'cash') => 'Gasto en efectivo', // agregado a mano sin comercio (Paso 15B)
      _ => 'Transferencia',
    };

class MovementCard extends StatelessWidget {
  const MovementCard({super.key, required this.movement, required this.now, required this.onTap, this.grouped = false});

  final Map<String, dynamic> movement;
  final DateTime now;
  final VoidCallback onTap;

  /// Dentro de un grupo por día: solo la hora (el día ya está en el título del grupo).
  final bool grouped;

  @override
  Widget build(BuildContext context) {
    final m = movement;
    final details = [m['categoria'] ?? 'Sin categoría', ?kindNote(m)];
    final info = Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title(m), style: Fsf.tarjeta),
        if (m['estado'] == 'pending_review')
          const Text(pendingLabel, style: TextStyle(fontWeight: FontWeight.w700, fontSize: 12)),
        const SizedBox(height: 4),
        Text(details.join(' · '), style: Fsf.secundario),
      ],
    );
    final amount = Text(signedAmount(m), style: Fsf.montoTarjeta);
    final fecha = m['fecha'] as String;
    final date = Text(grouped ? timeLabel(fecha) : dateLabel(fecha, now), style: Fsf.secundario);
    // Icono de la categoría en un cuadro gris (Paso 15B).
    final icon = ExcludeSemantics(
      child: Container(
        width: 40,
        height: 40,
        decoration: const BoxDecoration(color: Fsf.borde, borderRadius: BorderRadius.all(Radius.circular(12))),
        child: Icon(categoryIcon(m['categoria'] as String?), size: 22, color: Fsf.texto),
      ),
    );
    // Con el texto grande no caben dos columnas: el monto va debajo, sin partir el comercio.
    final large = MediaQuery.textScalerOf(context).scale(16) > 16 * 1.4;
    return Card(
      clipBehavior: Clip.antiAlias,
      child: InkWell(
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: large
              ? Column(
                  crossAxisAlignment: CrossAxisAlignment.stretch,
                  children: [info, const SizedBox(height: 8), amount, date],
                )
              : Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    icon,
                    const SizedBox(width: 12),
                    Expanded(child: info),
                    const SizedBox(width: 12),
                    Column(
                      crossAxisAlignment: CrossAxisAlignment.end,
                      children: [amount, const SizedBox(height: 4), date],
                    ),
                  ],
                ),
        ),
      ),
    );
  }
}

/// Hoja inferior: categoría con un toque y, si está por confirmar, confirmar o descartar.
class MovementSheet extends StatefulWidget {
  const MovementSheet({
    super.key,
    required this.api,
    required this.movement,
    required this.now,
    required this.onChanged,
  });

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
    final m = widget.movement, id = m['id'];
    final pending = m['estado'] == 'pending_review', income = m['direccion'] == 'income';
    final amount = formatCop(m['monto'] as String);
    return SafeArea(
      child: SingleChildScrollView(
        padding: const EdgeInsets.fromLTRB(Fsf.margen, 0, Fsf.margen, Fsf.margen),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // Como en «Categorizar gasto» de Figma: por confirmar, o categoría que no se supo (Paso 14).
            if (pending || m['preguntar_categoria'] == true)
              Align(
                alignment: Alignment.centerLeft,
                child: CircleAvatar(
                  radius: 20,
                  backgroundColor: Fsf.superficie,
                  child: Icon(
                    Icons.error_outline,
                    color: Fsf.texto,
                    semanticLabel: pending ? 'Por confirmar' : 'Categoría por elegir',
                  ),
                ),
              ),
            const SizedBox(height: 16),
            Text(
              income ? '¿A qué categoría pertenece este movimiento?' : '¿A qué categoría pertenece este gasto?',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 26, height: 1.2),
            ),
            const SizedBox(height: 12),
            Text(
              '$amount ${income ? 'de' : 'en'} ${title(m)}',
              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 38, height: 1.12),
            ),
            const SizedBox(height: 8),
            Text(
              [dateLabel(m['fecha'] as String, widget.now), if (pending) 'Por confirmar'].join(' · '),
              style: Fsf.ayuda,
            ),
            const SizedBox(height: 24),
            const Text('Categorías', style: TextStyle(fontWeight: FontWeight.w600, fontSize: 16)),
            const SizedBox(height: 12),
            LayoutBuilder(
              builder: (context, box) => Wrap(
                spacing: 12,
                runSpacing: 12,
                children: [
                  // «Ingresos» solo se ofrece en los ingresos, nunca en un gasto.
                  for (final c in _categories.where((c) => income || c['name'] != 'Ingresos'))
                    SizedBox(
                      width: (box.maxWidth - 12) / 2, // dos por fila
                      child: CategoryOption(
                        label: c['name'] as String,
                        selected: _selected == c['id'],
                        onTap: _busy
                            ? null
                            : () => _run(() async {
                                await widget.api.patch('/transactions/$id/category', {'category_id': c['id']});
                                if (mounted) setState(() => _selected = c['id'] as String);
                              }),
                      ),
                    ),
                ],
              ),
            ),
            if (_error != null) Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
            if (pending) ...[
              const SizedBox(height: 24),
              FilledButton(
                onPressed: _busy ? null : () => _run(() => widget.api.post('/transactions/$id/confirm'), close: true),
                child: const Text('Confirmar'),
              ),
              const SizedBox(height: 8),
              TextButton(
                style: TextButton.styleFrom(foregroundColor: Fsf.textoSecundario),
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

/// Categoría de la hoja: píldora gris (negra si está elegida), alto mínimo 64.
class CategoryOption extends StatelessWidget {
  const CategoryOption({super.key, required this.label, required this.selected, required this.onTap});

  final String label;
  final bool selected;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) => Semantics(
    selected: selected,
    button: true,
    child: Material(
      color: selected ? Fsf.primario : Fsf.superficie,
      shape: const StadiumBorder(),
      child: InkWell(
        customBorder: const StadiumBorder(),
        onTap: onTap,
        child: ConstrainedBox(
          constraints: const BoxConstraints(minHeight: 64),
          child: Center(
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
              child: Text(
                label,
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontWeight: FontWeight.w600,
                  fontSize: 15,
                  color: selected ? Fsf.sobrePrimario : Fsf.texto,
                ),
              ),
            ),
          ),
        ),
      ),
    ),
  );
}
