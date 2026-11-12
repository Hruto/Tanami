
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../widgets/auth_button.dart';
import '../widgets/auth_text_field.dart';

import '../models/register_request.dart';
import '../services/auth_service.dart';

class RegisterPage extends StatefulWidget {
  const RegisterPage({super.key});

  @override
  State<RegisterPage> createState() => _RegisterPageState();
  
}

class _RegisterPageState extends State<RegisterPage> {
  bool _obscurePassword = true;
  bool _obscureConfirmPassword = true;
  bool _isLoading = false;

final _fullNameController = TextEditingController();
final _usernameController = TextEditingController();
final _emailController = TextEditingController();
final _passwordController = TextEditingController();
final _confirmPasswordController = TextEditingController();

  @override
  void dispose() {
    _fullNameController.dispose();
    _usernameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();
    super.dispose();
  }

  
Future<void> _register() async {
  if (_fullNameController.text.trim().isEmpty ||
      _usernameController.text.trim().isEmpty ||
      _emailController.text.trim().isEmpty ||
      _passwordController.text.isEmpty ||
      _confirmPasswordController.text.isEmpty) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Semua kolom wajib diisi.'),
      ),
    );
    return;
  }

  if (_passwordController.text !=
      _confirmPasswordController.text) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Konfirmasi kata sandi tidak sama.'),
      ),
    );
    return;
  }

  setState(() => _isLoading = true);

  try {
    final request = RegisterRequest(
      fullName: _fullNameController.text.trim(),
      username: _usernameController.text.trim(),
      email: _emailController.text.trim(),
      password: _passwordController.text,
      consentTrainingData: false,
    );

    await AuthService().register(request);

    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Registrasi berhasil!'),
      ),
    );

    Navigator.pushReplacementNamed(context, '/login');
  } catch (e) {
    if (!mounted) return;

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          e.toString().replaceFirst('Exception: ', ''),
        ),
      ),
    );
  } finally {
    if (mounted) {
      setState(() => _isLoading = false);
    }
  }
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
                    'assets/images/logo_tanami.svg',
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
                  label: 'Nama Lengkap',
                  hint: 'Anonim',
                  icon: Icons.person_outline,
                  controller: _fullNameController,
                ),

                const SizedBox(height: 20),

                AuthTextField(
                  label: 'Username',
                  hint: 'tanamiuser',
                  icon: Icons.alternate_email,
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
                  text: _isLoading ? 'Memproses...' : 'Daftar',
                  onPressed: _isLoading ? null : _register,
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
