/// Montos en COP como texto, sin double (RQN 03): el backend envía "1234567.89" y aquí solo se
/// formatea ese texto. Nunca se calcula con double ni se usa NumberFormat sobre un double.
library;

final _amount = RegExp(r'^(-)?(\d+)(?:\.(\d{1,2}))?$');

/// Espacio duro: "$ 1.234" no se parte en dos líneas.
const nbsp = ' ';

/// "1234567.89" → "$ 1.234.567,89" · "-66666.00" → "-$ 66.666" · "0.50" → "$ 0,50".
/// Miles con punto; sin decimales cuando son ,00.
String formatCop(String amount) {
  final m = _amount.firstMatch(amount.trim());
  if (m == null) throw FormatException('Monto inválido', amount);
  final digits = m[2]!.replaceFirst(RegExp(r'^0+(?=\d)'), '');
  final cents = (m[3] ?? '').padRight(2, '0');
  final grouped = _group(digits);
  final text = cents == '00' ? grouped : '$grouped,$cents';
  final negative = m[1] != null && !(digits == '0' && cents == '00');
  return '${negative ? '-' : ''}\$$nbsp$text';
}

/// Solo el número, para prellenar un campo: "700000.00" → "700.000".
String formatNumber(String amount) => formatCop(amount).replaceFirst(RegExp('^-?\\\$$nbsp'), '');

String _group(String digits) {
  final out = StringBuffer();
  for (var i = 0; i < digits.length; i++) {
    if (i > 0 && (digits.length - i) % 3 == 0) out.write('.');
    out.write(digits[i]);
  }
  return out.toString();
}

/// Centavos exactos como BigInt, solo para comparar o decidir el signo (nunca para mostrar).
BigInt cents(String amount) {
  final m = _amount.firstMatch(amount.trim());
  if (m == null) throw FormatException('Monto inválido', amount);
  final value = BigInt.parse(m[2]!) * BigInt.from(100) + BigInt.parse((m[3] ?? '').padRight(2, '0'));
  return m[1] != null ? -value : value;
}

bool isNegativeAmount(String amount) => cents(amount) < BigInt.zero;
bool isPositiveAmount(String amount) => cents(amount) > BigInt.zero;

/// Valor absoluto como texto: "-66666.00" → "66666.00".
String absolute(String amount) => amount.trim().replaceFirst('-', '');

final _plain = RegExp(r'^\d{1,12}$');
final _thousands = RegExp(r'^\d{1,3}(\.\d{3}){1,3}$');

/// Lo que escribe el usuario → monto canónico para el backend ("1500000" o "1500000.5"), o null
/// si no es un monto válido mayor que 0. Acepta "1500000", "1.500.000", "$ 1.500.000,50".
String? parseCopInput(String text) {
  var t = text.replaceAll(RegExp(r'[\s$ ]'), '');
  String? decimals;
  final comma = t.indexOf(',');
  if (comma >= 0) {
    decimals = t.substring(comma + 1);
    t = t.substring(0, comma);
    if (!RegExp(r'^\d{1,2}$').hasMatch(decimals)) return null;
  }
  if (_thousands.hasMatch(t)) {
    t = t.replaceAll('.', '');
  } else if (!_plain.hasMatch(t)) {
    return null;
  }
  final canonical = decimals == null ? t : '$t.$decimals';
  return cents(canonical) > BigInt.zero ? canonical : null;
}
