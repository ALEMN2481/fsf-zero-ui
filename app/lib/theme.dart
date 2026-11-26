import 'package:flutter/material.dart';

/// Tokens de docs/design/tokens.md (Figma, con las correcciones de contraste que mandan; D14).
abstract final class Fsf {
  static const fondo = Color(0xFFFFFFFF);
  static const superficie = Color(0xFFF1F5F9);
  static const texto = Color(0xFF000000);
  static const textoSecundario = Color(0xFF64748B); // solo sobre blanco (4,76:1)
  static const textoSecundarioEnSuperficie = Color(0xFF475569); // sobre superficie (6,92:1)
  static const textoTenue = Color(0xFF94A3B8); // solo marcadores de posición
  static const borde = Color(0xFFE2E8F0);
  static const primario = Color(0xFF000000);
  static const sobrePrimario = Color(0xFFFFFFFF);
  static const asaHoja = Color(0xFFD3D3D3);
  static const arranqueFondo = Color(0xFF0D0D11);
  static const arranqueTextoSecundario = Color(0xFFA6A6AE);
  static const arranquePista = Color(0xFF29292F);
  static const globo = Color(0xFF222222); // globos del tutorial

  static const margen = 24.0;

  /// Cifra grande (Unbounded Medium 40): siempre dentro de un FittedBox.
  static const cifra = TextStyle(fontFamily: 'Unbounded', fontWeight: FontWeight.w500, fontSize: 40, color: texto);
  static const tituloSeccion = TextStyle(
    fontFamily: 'Unbounded',
    fontWeight: FontWeight.w700,
    fontSize: 16,
    color: texto,
  );
  static const montoTarjeta = TextStyle(
    fontFamily: 'Unbounded',
    fontWeight: FontWeight.w700,
    fontSize: 14,
    color: texto,
  );
  static const etiqueta = TextStyle(
    fontFamily: 'Inter',
    fontWeight: FontWeight.w600,
    fontSize: 14,
    color: textoSecundario,
    letterSpacing: 0.5,
  );
  static const tarjeta = TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600, fontSize: 16, color: texto);
  static const secundario = TextStyle(fontFamily: 'Inter', fontSize: 12, color: textoSecundarioEnSuperficie);
  static const ayuda = TextStyle(fontFamily: 'Inter', fontSize: 12, color: textoSecundario);
}

ThemeData fsfTheme() {
  const pill = StadiumBorder();
  final base = ThemeData(useMaterial3: true, fontFamily: 'Inter');
  return base.copyWith(
    colorScheme: const ColorScheme.light(
      primary: Fsf.primario,
      onPrimary: Fsf.sobrePrimario,
      secondary: Fsf.superficie,
      onSecondary: Fsf.texto,
      surface: Fsf.fondo,
      onSurface: Fsf.texto,
      onSurfaceVariant: Fsf.textoSecundario,
      surfaceContainerHighest: Fsf.superficie,
      surfaceContainerHigh: Fsf.superficie,
      surfaceContainer: Fsf.superficie,
      surfaceContainerLow: Fsf.superficie,
      outline: Fsf.borde,
      outlineVariant: Fsf.borde,
      error: Color(0xFFB3261E),
    ),
    scaffoldBackgroundColor: Fsf.fondo,
    appBarTheme: const AppBarTheme(
      backgroundColor: Fsf.fondo,
      foregroundColor: Fsf.texto,
      elevation: 0,
      scrolledUnderElevation: 0,
      titleTextStyle: TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700, fontSize: 18, color: Fsf.texto),
    ),
    cardTheme: const CardThemeData(
      color: Fsf.superficie,
      elevation: 0,
      margin: EdgeInsets.symmetric(vertical: 4),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(16))),
    ),
    filledButtonTheme: FilledButtonThemeData(
      style: FilledButton.styleFrom(
        backgroundColor: Fsf.primario,
        foregroundColor: Fsf.sobrePrimario,
        minimumSize: const Size(48, 60),
        shape: pill,
        textStyle: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w700, fontSize: 16),
      ),
    ),
    // Botón secundario (p. ej. Google): gris claro, píldora de 56.
    outlinedButtonTheme: OutlinedButtonThemeData(
      style: OutlinedButton.styleFrom(
        backgroundColor: Fsf.superficie,
        foregroundColor: Fsf.texto,
        side: BorderSide.none,
        minimumSize: const Size(48, 56),
        shape: pill,
        textStyle: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600, fontSize: 15),
      ),
    ),
    textButtonTheme: TextButtonThemeData(
      style: TextButton.styleFrom(
        foregroundColor: Fsf.texto,
        minimumSize: const Size(48, 48),
        shape: pill,
        textStyle: const TextStyle(fontFamily: 'Inter', fontWeight: FontWeight.w600, fontSize: 15),
      ),
    ),
    floatingActionButtonTheme: const FloatingActionButtonThemeData(
      backgroundColor: Fsf.primario,
      foregroundColor: Fsf.sobrePrimario,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(28))),
      sizeConstraints: BoxConstraints.tightFor(width: 60, height: 60),
    ),
    inputDecorationTheme: const InputDecorationTheme(
      filled: true,
      fillColor: Fsf.superficie,
      hintStyle: TextStyle(color: Fsf.textoTenue),
      contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 18),
      border: OutlineInputBorder(borderRadius: BorderRadius.all(Radius.circular(16)), borderSide: BorderSide.none),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(16)),
        borderSide: BorderSide.none,
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.all(Radius.circular(16)),
        borderSide: BorderSide(color: Fsf.texto, width: 1.5),
      ),
    ),
    bottomSheetTheme: const BottomSheetThemeData(
      backgroundColor: Fsf.fondo,
      showDragHandle: true,
      dragHandleColor: Fsf.asaHoja,
      dragHandleSize: Size(36, 4),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(32))),
    ),
    progressIndicatorTheme: const ProgressIndicatorThemeData(
      color: Fsf.primario,
      linearTrackColor: Fsf.borde,
      linearMinHeight: 8,
    ),
    popupMenuTheme: const PopupMenuThemeData(
      color: Fsf.fondo,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(16))),
    ),
    // Mensajes breves y avisos con la app abierta (Paso 14): negro, texto blanco, esquinas de tarjeta.
    snackBarTheme: const SnackBarThemeData(
      backgroundColor: Fsf.primario,
      behavior: SnackBarBehavior.floating,
      elevation: 0,
      insetPadding: EdgeInsets.fromLTRB(Fsf.margen, 0, Fsf.margen, 16),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.all(Radius.circular(16))),
      contentTextStyle: TextStyle(
        fontFamily: 'Inter',
        fontWeight: FontWeight.w600,
        fontSize: 15,
        color: Fsf.sobrePrimario,
      ),
      actionTextColor: Fsf.sobrePrimario,
    ),
  );
}
