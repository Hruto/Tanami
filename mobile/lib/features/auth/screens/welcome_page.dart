
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../widgets/auth_button.dart';
import '../../../core/constant/app_colors.dart';

class WelcomePage extends StatelessWidget {
  const WelcomePage({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
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
                  color: AppColors.grey,
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
                  color:AppColors.grey,
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
