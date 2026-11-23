
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';
import '../widgets/auth_button.dart';
import '../widgets/auth_text_field.dart';
import '../models/login_request.dart';
import '../services/auth_service.dart';

class LoginPage extends StatefulWidget {
  const LoginPage({super.key});

  @override
  State<LoginPage> createState() => _LoginPageState();
}

class _LoginPageState extends State<LoginPage> {
  bool _obscurePassword = true;
  bool _isLoading = false;

  final _usernameController = TextEditingController();
  final _passwordController = TextEditingController();

  String? _usernameError;
  String? _passwordError;

  @override
  void initState() {
    super.initState();

    _usernameController.addListener(_onUsernameChanged);
    _passwordController.addListener(_onPasswordChanged);
  }

  void _onUsernameChanged() {
    if (_usernameError != null) {
      setState(() {
        _usernameError = _usernameController.text.trim().isEmpty
            ? 'Nama pengguna wajib diisi.'
            : null;
      });
    }
  }

  void _onPasswordChanged() {
    if (_passwordError != null) {
      setState(() {
        _passwordError = _passwordController.text.isEmpty
            ? 'Kata sandi wajib diisi.'
            : null;
      });
    }
  }

  @override
  void dispose() {
    _usernameController.removeListener(_onUsernameChanged);
    _passwordController.removeListener(_onPasswordChanged);

    _usernameController.dispose();
    _passwordController.dispose();

    super.dispose();
  }

  void _showTanamiSnackBar({
    required String title,
    required String message,
    required bool isSuccess,
  }) {
    final color = isSuccess
        ? AppColors.mediumGreen
        : AppColors.red;

    final backgroundColor = isSuccess
        ? AppColors.lightGreen.withValues(alpha: 0.25)
        : AppColors.red.withValues(alpha: 0.10);

    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          behavior: SnackBarBehavior.floating,
          backgroundColor: Colors.transparent,
          elevation: 0,
          duration: const Duration(seconds: 3),
          padding: const EdgeInsets.symmetric(horizontal: 12),
          content: Container(
            padding: const EdgeInsets.all(14),
            decoration: BoxDecoration(
              color: backgroundColor,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.06),
                  blurRadius: 10,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: Row(
              children: [
                Icon(
                  isSuccess
                      ? Icons.check_circle_outline
                      : Icons.error_outline,
                  color: color,
                  size: 25,
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          fontFamily: 'Alexandria',
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: color,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        message,
                        style: const TextStyle(
                          fontFamily: 'Alexandria',
                          fontSize: 10,
                          color: AppColors.darkGreen,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
  }

  Future<void> _login() async {
    FocusScope.of(context).unfocus();

    setState(() {
      _usernameError = _usernameController.text.trim().isEmpty
          ? 'Nama pengguna wajib diisi.'
          : null;

      _passwordError = _passwordController.text.isEmpty
          ? 'Kata sandi wajib diisi.'
          : null;
    });

    if (_usernameError != null || _passwordError != null) {
      return;
    }

    setState(() {
      _isLoading = true;
    });

    try {
      final request = LoginRequest(
        username: _usernameController.text.trim(),
        password: _passwordController.text,
      );

      await AuthService().login(request);

      if (!mounted) return;

      _showTanamiSnackBar(
        title: 'Selamat Datang Kembali!',
        message: 'Login berhasil. Selamat menggunakan Tanami.',
        isSuccess: true,
      );

      Navigator.pushNamedAndRemoveUntil(
        context,
        '/home',
        (route) => false,
      );
    } catch (e) {
      if (!mounted) return;

      _showTanamiSnackBar(
        title: 'Login Gagal',
        message: e.toString().replaceFirst('Exception: ', ''),
        isSuccess: false,
      );
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
 @override
Widget build(BuildContext context) {
  return Scaffold(
    backgroundColor: AppColors.background,
    body: SafeArea(
      child: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: constraints.maxHeight,
              ),
              child: IntrinsicHeight(
                child: Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 20),
                  child: Column(
                    children: [
                      // AREA TENGAH
                      Expanded(
                        child: Center(
                          child: Column(
                            mainAxisSize: MainAxisSize.min,
                            crossAxisAlignment: CrossAxisAlignment.stretch,
                            children: [
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
                                  'Selamat Datang Kembali!',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontFamily: 'Alexandria',
                                    fontSize: 22,
                                    fontWeight: FontWeight.w700,
                                    color: AppColors.darkGreen,
                                  ),
                                ),
                              ),

                              const SizedBox(height: 45),

                              AuthTextField(
                                label: 'Nama Pengguna',
                                hint: 'Masukan nama pengguna',
                                iconAsset:
                                    'assets/icons/person_outline.svg',
                                controller: _usernameController,
                                errorText: _usernameError,
                              ),

                              const SizedBox(height: 20),

                              AuthTextField(
                                label: 'Kata Sandi',
                                hint: 'Masukan kata sandi',
                                iconAsset: 'assets/icons/lock.svg',
                                controller: _passwordController,
                                isPassword: true,
                                obscureText: _obscurePassword,
                                errorText: _passwordError,
                                onTogglePassword: () {
                                  setState(() {
                                    _obscurePassword =
                                        !_obscurePassword;
                                  });
                                },
                              ),
                            ],
                          ),
                        ),
                      ),

                      // AREA BAWAH
                      AuthButton(
                        text: _isLoading ? 'Memproses...' : 'Masuk',
                        onPressed: _isLoading ? null : _login,
                      ),

                      const SizedBox(height: 12),

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
                                color: AppColors.mediumGreen,
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

                      const SizedBox(height: 20),
                    ],
                  ),
                ),
              ),
            ),
          );
        },
      ),
    ),
  );
}
}
