import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import 'api.dart';
import 'money.dart';
import 'movements.dart' show CategoryOption;
import 'theme.dart';

const savedCounted = 'Gasto agregado';
const savedFromWithdrawal = 'Gasto agregado · Ya estaba contado en tu retiro';
const maxAmountDigits = 12; // como el tope del backend (numeric(14, 2))

/// Agregar un gasto a mano (Paso 15B), una pregunta por pantalla: monto → categoría → comercio.
/// Siempre en efectivo: no descuenta del presupuesto (ya se contó en el retiro, D12) salvo que el
/// usuario marque «No salió de un retiro». Devuelve el mensaje para mostrar al guardar.
class ManualExpenseScreen extends StatefulWidget {
  const ManualExpenseScreen({super.key, required this.api});

  final Api api;

  @override
  State<ManualExpenseScreen> createState() => _ManualExpenseScreenState();
}

class _ManualExpenseScreenState extends State<ManualExpenseScreen> {
  int _step = 0;
  String _digits = ''; // el monto en pesos, solo dígitos: nunca double (RQN 03)
  String? _category;
  bool _notFromWithdrawal = false, _saving = false;
  String? _error;
  final _merchant = TextEditingController();
  List<Map<String, dynamic>> _categories = const [];

  static const _questions = ['¿Cuánto gastaste?', '¿En qué categoría?', '¿Dónde fue?'];

  @override
  void initState() {
    super.initState();
    widget.api.get('/categories').then((rows) {
      if (!mounted) return;
      setState(
        () => _categories = (rows as List)
            .cast<Map<String, dynamic>>()
            .where((c) => c['name'] != 'Ingresos') // solo gastos
            .toList(),
      );
    }, onError: (_) {});
  }

  @override
  void dispose() {
    _merchant.dispose();
    super.dispose();
  }

  bool get _amountOk => _digits.isNotEmpty && BigInt.parse(_digits) > BigInt.zero;

  void _back() => _step == 0 ? Navigator.of(context).pop() : setState(() => _step--);

  Future<void> _save() async {
    setState(() {
      _saving = true;
      _error = null;
    });
    try {
      final merchant = _merchant.text.trim();
      await widget.api.post('/transactions', {
        'monto': _digits,
        'category_id': _category,
        if (merchant.isNotEmpty) 'comercio': merchant,
        'fuera_de_retiro': _notFromWithdrawal,
      });
      if (mounted) Navigator.of(context).pop(_notFromWithdrawal ? savedCounted : savedFromWithdrawal);
    } catch (_) {
      if (mounted) setState(() => _error = 'No se pudo guardar, inténtalo de nuevo');
    } finally {
      if (mounted) setState(() => _saving = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return PopScope(
      canPop: _step == 0,
      onPopInvokedWithResult: (didPop, _) {
        if (!didPop) _back();
      },
      child: Scaffold(
        appBar: AppBar(
          leading: IconButton(tooltip: 'Atrás', icon: const Icon(Icons.arrow_back), onPressed: _back),
          title: const Text('Agregar gasto'),
        ),
        body: SafeArea(
          child: ListView(
            padding: const EdgeInsets.all(Fsf.margen),
            children: [
              Semantics(
                label: 'Paso ${_step + 1} de 3',
                child: ExcludeSemantics(child: LinearProgressIndicator(value: (_step + 1) / 3)),
              ),
              const SizedBox(height: 24),
              Text(_questions[_step], style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 26, height: 1.2)),
              const SizedBox(height: 24),
              ...switch (_step) {
                0 => _amountStep(),
                1 => _categoryStep(),
                _ => _merchantStep(),
              },
            ],
          ),
        ),
      ),
    );
  }

  List<Widget> _amountStep() => [
    TextField(
      key: const Key('monto'),
      autofocus: true,
      keyboardType: TextInputType.number,
      inputFormatters: [FilteringTextInputFormatter.digitsOnly, const _ThousandsFormatter()],
      style: Fsf.cifra.copyWith(fontSize: 32),
      // El «0» de ayuda en gris secundario: el tenue no llega a 3:1 en cifras grandes.
      decoration: const InputDecoration(
        prefixText: '\$$nbsp',
        hintText: '0',
        hintStyle: TextStyle(color: Fsf.textoSecundario),
      ),
      onChanged: (text) => setState(() => _digits = text.replaceAll('.', '')),
    ),
    const SizedBox(height: 8),
    const Text('Gastos en efectivo: lo que pagaste con tarjeta o transferencia llega solo.', style: Fsf.ayuda),
    const SizedBox(height: 24),
    FilledButton(onPressed: _amountOk ? () => setState(() => _step = 1) : null, child: const Text('Continuar')),
  ];

  List<Widget> _categoryStep() => [
    LayoutBuilder(
      builder: (context, box) => Wrap(
        spacing: 12,
        runSpacing: 12,
        children: [
          for (final c in _categories)
            SizedBox(
              width: (box.maxWidth - 12) / 2,
              child: CategoryOption(
                label: c['name'] as String,
                selected: _category == c['id'],
                onTap: () => setState(() => _category = c['id'] as String),
              ),
            ),
        ],
      ),
    ),
    const SizedBox(height: 24),
    FilledButton(onPressed: _category == null ? null : () => setState(() => _step = 2), child: const Text('Continuar')),
  ];

  List<Widget> _merchantStep() => [
    TextField(
      key: const Key('comercio'),
      controller: _merchant,
      maxLength: 60,
      textCapitalization: TextCapitalization.characters,
      decoration: const InputDecoration(hintText: 'Comercio (opcional)'),
    ),
    const SizedBox(height: 8),
    CheckboxListTile(
      contentPadding: EdgeInsets.zero,
      controlAffinity: ListTileControlAffinity.leading,
      value: _notFromWithdrawal,
      onChanged: (v) => setState(() => _notFromWithdrawal = v ?? false),
      title: const Text('No salió de un retiro'),
      subtitle: const Text(
        'Si sacaste ese efectivo del cajero, ya lo contamos en el retiro y no vuelve a descontarse.',
        style: Fsf.ayuda,
      ),
    ),
    if (_error != null) ...[
      const SizedBox(height: 8),
      Text(_error!, style: TextStyle(color: Theme.of(context).colorScheme.error)),
    ],
    const SizedBox(height: 24),
    FilledButton(onPressed: _saving ? null : _save, child: const Text('Guardar gasto')),
  ];
}

/// "12500" → "12.500" mientras se escribe (solo dígitos, con tope).
class _ThousandsFormatter extends TextInputFormatter {
  const _ThousandsFormatter();

  @override
  TextEditingValue formatEditUpdate(TextEditingValue old, TextEditingValue value) {
    var digits = value.text.replaceAll('.', '').replaceFirst(RegExp(r'^0+(?=\d)'), '');
    if (digits.length > maxAmountDigits) return old;
    if (digits.isEmpty) return const TextEditingValue();
    final text = formatNumber(digits);
    return TextEditingValue(
      text: text,
      selection: TextSelection.collapsed(offset: text.length),
    );
  }
}
