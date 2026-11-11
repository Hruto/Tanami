
import 'package:flutter/material.dart';

import 'core/theme/app_theme.dart';
import 'features/auth/screens/welcome_page.dart';
import 'features/auth/screens/login_page.dart';
import 'features/auth/screens/register_page.dart';

void main() {
  runApp(const TanamiApp());
}

class TanamiApp extends StatelessWidget {
  const TanamiApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Tanami',
      theme: AppTheme.lightTheme,
      initialRoute: '/',
      routes: {
        '/': (context) => const WelcomePage(),
        '/login': (context) => const LoginPage(),
        '/register': (context) => const RegisterPage(),
      },
    );
  }
}
