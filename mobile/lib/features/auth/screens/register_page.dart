
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../widgets/auth_button.dart';
import '../widgets/auth_text_field.dart';

class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
}

class _RegisterPageState extends State<RegisterPage> {
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;

  final _usernameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  final _confirmPasswordController = TextEditingController();

  @override
  void dispose() {
    _usernameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF8FAF7),
      body: SafeArea(
        child: SingleChildScrollView(
          child: Padding(
            padding: const EdgeInsets.symmetric(horizontal: 20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const SizedBox(height: 65),

                Center(
                  child: SvgPicture.asset(
                    'assets/images/splash_logo.png',
                    width: 65,
                    height: 75,
                    fit: BoxFit.contain,
                  ),
                ),

                const SizedBox(height: 10),

                const Center(
                  child: Text(
                    'Selamat Datang!',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF344236),
                    ),
                  ),
                ),

                const SizedBox(height: 55),

                AuthTextField(
                  label: 'Nama Pengguna',
                  hint: 'Anonim',
                  icon: Icons.person_outline,
                  controller: _usernameController,
                ),

                const SizedBox(height: 20),

                AuthTextField(
                  label: 'Email',
                  hint: 'Anonim@gmail.com',
                  icon: Icons.mail_outline,
                  controller: _emailController,
                  keyboardType: TextInputType.emailAddress,
                ),

                const SizedBox(height: 20),

                AuthTextField(
                  label: 'Kata Sandi',
                  hint: '••••••••••••',
                  icon: Icons.lock_outline,
                  controller: _passwordController,
                  isPassword: true,
                  obscureText: _obscurePassword,
                  onTogglePassword: () {
                    setState(() {
                      _obscurePassword = !_obscurePassword;
                    });
                  },
                ),

                const SizedBox(height: 20),

                AuthTextField(
                  label: 'Konfirmasi Kata Sandi',
                  hint: '••••••••••••',
                  icon: Icons.lock_outline,
                  controller: _confirmPasswordController,
                  isPassword: true,
                  obscureText: _obscureConfirmPassword,
                  onTogglePassword: () {
                    setState(() {
                      _obscureConfirmPassword =
                          !_obscureConfirmPassword;
                    });
                  },
                ),

                const SizedBox(height: 70),

                AuthButton(
                  text: 'Daftar',
                  onPressed: () {
                    // Proses registrasi akan dihubungkan ke API nanti.
                  },
                ),

                const SizedBox(height: 10),

                Center(
                  child: GestureDetector(
                    onTap: () {
                      Navigator.pushReplacementNamed(
                        context,
                        '/login',
                      );
                    },
                    child: RichText(
                      text: const TextSpan(
                        style: TextStyle(
                          fontFamily: 'Alexandria',
                          fontSize: 11,
                          color: Color(0xFF6B8F70),
                        ),
                        children: [
                          TextSpan(
                            text: 'Sudah memiliki akun? ',
                          ),
                          TextSpan(
                            text: 'Masuk',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

                const SizedBox(height: 35),
              ],
            ),
          ),
        ),
      ),
    );
  }
}
