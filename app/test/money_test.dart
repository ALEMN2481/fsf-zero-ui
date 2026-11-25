import 'package:flutter_test/flutter_test.dart';
import 'package:fsf_app/money.dart';

String cop(String s) => s.replaceAll(nbsp, ' '); // para leer los esperados

void main() {
  group('formatCop formatea el texto que llega, sin double', () {
    for (final (input, expected) in [
      ('0.00', '\$ 0'),
      ('5', '\$ 5'),
      ('999.00', '\$ 999'),
      ('1000.00', '\$ 1.000'),
      ('23500.00', '\$ 23.500'),
      ('1234567.89', '\$ 1.234.567,89'),
      ('0.50', '\$ 0,50'),
      ('10.5', '\$ 10,50'),
      ('-66666.00', '-\$ 66.666'),
      ('-0.01', '-\$ 0,01'),
      ('-0.00', '\$ 0'), // sin "-0"
      ('999999999999.99', '\$ 999.999.999.999,99'), // máximo de numeric(14,2)
      ('12345678901234567890.10', '\$ 12.345.678.901.234.567.890,10'), // sin pérdida, a diferencia de double
      ('007.00', '\$ 7'),
    ]) {
      test('$input → $expected', () => expect(cop(formatCop(input)), expected));
    }

    test('rechaza lo que no es un monto', () {
      for (final bad in ['', 'abc', '1,5', '1.234.567', '1.234', '\$5', '1e5', 'NaN']) {
        expect(() => formatCop(bad), throwsFormatException, reason: bad);
      }
    });

    test('el símbolo y la cifra no se separan de línea', () => expect(formatCop('1.00'), contains(nbsp)));
  });

  test('formatNumber deja solo la cifra para prellenar un campo', () {
    expect(formatNumber('700000.00'), '700.000');
    expect(formatNumber('-1500.25'), '1.500,25');
  });

  test('cents compara exacto con BigInt', () {
    expect(cents('486666.00') < cents('500000.00'), isTrue);
    expect(cents('-0.01'), BigInt.from(-1));
    expect(cents('99999999999999999999.99').toString(), '9999999999999999999999');
    expect(isNegativeAmount('-1.00') && isPositiveAmount('0.01') && !isPositiveAmount('0.00'), isTrue);
    expect(absolute('-66666.00'), '66666.00');
  });

  group('parseCopInput acepta lo que escribe el usuario', () {
    for (final (input, expected) in [
      ('1500000', '1500000'),
      ('1.500.000', '1500000'),
      (r'$ 1.500.000', '1500000'),
      ('1.500.000,5', '1500000.5'),
      ('2500000,50', '2500000.50'),
      (' 700 ', '700'),
      ('1$nbsp' '000', '1000'),
    ]) {
      test('"$input" → $expected', () => expect(parseCopInput(input), expected));
    }

    test('rechaza ambiguos, vacíos, cero, negativos y demasiado grandes', () {
      for (final bad in ['', '0', '0,00', '-5', '1.5', '1,234,567', '1.50.000', '12,345', 'diez', '1234567890123']) {
        expect(parseCopInput(bad), isNull, reason: bad);
      }
    });
  });
}
