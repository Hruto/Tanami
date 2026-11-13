
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../widgets/auth_button.dart';

class WelcomePage extends StatelessWidget {
  const WelcomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAF7),
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.symmetric(horizontal: 20),
          child: Column(
            children: [
              const Spacer(flex: 5),

              SvgPicture.asset(
                'assets/images/logo_tanami.svg',
                width: 190,
                fit: BoxFit.contain,
              ),

              const SizedBox(height: 10),

              const Text(
                'Temani setiap perjalanan tanamanmu,\n'
                'dari awal ditanam hingga waktu panen.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                  color: Color(0xFF6B7268),
                  height: 1.25,
                ),
              ),

              const Spacer(flex: 4),

              AuthButton(
                text: 'Masuk',
                onPressed: () {
                  Navigator.pushNamed(context, '/login');
                },
              ),

              const SizedBox(height: 12),

              AuthButton(
                text: 'Daftar',
                isSecondary: true,
                onPressed: () {
                  Navigator.pushNamed(context, '/register');
                },
              ),

              const SizedBox(height: 10),

              const Text(
                'Tumbuh Terpantau, Panen Lebih Terencana.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12,
                  color: Color(0xFF626A60),
                  fontWeight: FontWeight.w500,
                ),
              ),

              const SizedBox(height: 35),
            ],
          ),
        ),
      ),
    );
  }
}
