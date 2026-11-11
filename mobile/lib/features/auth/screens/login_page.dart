
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../widgets/auth_button.dart';
import '../widgets/auth_text_field.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  bool _obscurePassword = true;

  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();

  @override
  void dispose() {
    _usernameController.dispose();
    _passwordController.dispose();
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
                const SizedBox(height: 175),

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
                    'Selamat Datang Kembali!',
                    style: TextStyle(
                      fontSize: 22,
                      fontWeight: FontWeight.w700,
                      color: Color(0xFF344236),
                    ),
                  ),
                ),

                const SizedBox(height: 72),

                AuthTextField(
                  label: 'Nama Pengguna',
                  hint: 'Anonim',
                  icon: Icons.person_outline,
                  controller: _usernameController,
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

                const SizedBox(height: 10),

                Align(
                  alignment: Alignment.centerRight,
                  child: GestureDetector(
                    onTap: () {
                      // Fitur atur ulang kata sandi dibuat nanti.
                    },
                    child: RichText(
                      text: const TextSpan(
                        style: TextStyle(
                          fontFamily: 'Alexandria',
                          fontSize: 11,
                          color: Color(0xFF6B8F70),
                        ),
                        children: [
                          TextSpan(text: 'Lupa kata sandi? '),
                          TextSpan(
                            text: 'Atur ulang',
                            style: TextStyle(
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),

                const SizedBox(height: 90),

                AuthButton(
                  text: 'Masuk',
                  onPressed: () {
                    // Proses login dihubungkan ke API nanti.
                  },
                ),

                const SizedBox(height: 10),

                Center(
                  child: GestureDetector(
                    onTap: () {
                      Navigator.pushReplacementNamed(
                        context,
                        '/register',
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
                            text: 'Belum memiliki akun? ',
                          ),
                          TextSpan(
                            text: 'Daftar',
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
