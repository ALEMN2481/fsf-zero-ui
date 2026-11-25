import 'package:flutter/material.dart';

import 'api.dart';
import 'money.dart';

const amountHint = 'Escribe un monto válido, por ejemplo 1.500.000';

/// Presupuesto del mes con un solo campo (RQN 05). Se prellena con lo que se gastó el mes
/// anterior, nunca con el 100 % de los ingresos; las dos cifras se muestran como referencia.
class BudgetForm extends StatefulWidget {
  const BudgetForm({super.key, required this.api, required this.onSaved, this.current});

  final Api api;
  final VoidCallback onSaved;

  /// Monto vigente (al cambiarlo desde el menú); null la primera vez.
  final String? current;

  @override
  State<BudgetForm> createState() => _BudgetFormState();
}

class _BudgetFormState extends State<BudgetForm> {
  final _amount = TextEditingController();
  Map<String, dynamic>? _reference;
  String? _error;
  bool _saving = false;

  @override
  void initState() {
    super.initState();
    if (widget.current != null) _amount.text = formatNumber(widget.current!);
    _loadReference();
  }

  @override
  void dispose() {
    _amount.dispose();
    super.dispose();
  }

  Future<void> _loadReference() async {
    try {
      final ref = await widget.api.get('/budgets/suggestion') as Map<String, dynamic>;
      if (!mounted) return;
      setState(() => _reference = ref);
      final suggested = ref['sugerido'] as String?;
      if (_amount.text.isEmpty && suggested != null) _amount.text = formatNumber(suggested);
    } catch (_) {
      // Sin referencia el formulario sigue sirviendo.
    }
  }

  String? _referenceText() {
    final ref = _reference;
    if (ref == null) return null;
    final spent = ref['gasto_mes_anterior'] as String, earned = ref['ingresos_mes_anterior'] as String;
    if (isPositiveAmount(spent) && isPositiveAmount(earned)) {
      return 'El mes pasado gastaste ${formatCop(spent)} y te entraron ${formatCop(earned)}.';
    }
    if (isPositiveAmount(spent)) return 'El mes pasado gastaste ${formatCop(spent)}.';
    if (isPositiveAmount(earned)) return 'El mes pasado te entraron ${formatCop(earned)}.';
    return null;
  }

  Future<void> _save() async {
    final amount = parseCopInput(_amount.text);
    if (amount == null) {
      setState(() => _error = amountHint);
      return;
    }
    setState(() {
      _error = null;
      _saving = true;
    });
    try {
      await widget.api.post('/budgets', {'amount': amount});
      widget.onSaved();
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo guardar, inténtalo de nuevo');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final reference = _referenceText();
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Text('¿Cuánto quieres gastar este mes?', style: Theme.of(context).textTheme.headlineSmall),
        const SizedBox(height: 16),
        TextField(
          controller: _amount,
          keyboardType: const TextInputType.numberWithOptions(decimal: true),
          decoration: InputDecoration(labelText: 'Monto del mes', prefixText: '\$ ', errorText: _error),
          onSubmitted: (_) => _save(),
        ),
        if (reference != null) ...[const SizedBox(height: 12), Text(reference)],
        const SizedBox(height: 4),
        const Text('Se renueva solo cada mes.'),
        const SizedBox(height: 16),
        FilledButton(
          onPressed: _saving ? null : _save,
          child: Text(widget.current == null ? 'Empezar' : 'Guardar'),
        ),
      ],
    );
  }
}
