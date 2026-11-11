import 'package:flutter/material.dart';

class AppTheme {
  static ThemeData get lightTheme {
    return ThemeData(
      useMaterial3: true,
      fontFamily: 'Alexandria',
      scaffoldBackgroundColor: const Color(0xFFF8FAF7),
    );
  }
}