
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';
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

  String? _fullNameError;
  String? _usernameError;
  String? _emailError;
  String? _passwordError;
  String? _confirmPasswordError;

  @override
  void initState() {
    super.initState();

    _fullNameController.addListener(_onFullNameChanged);
    _usernameController.addListener(_onUsernameChanged);
    _emailController.addListener(_onEmailChanged);
    _passwordController.addListener(_onPasswordChanged);
    _confirmPasswordController.addListener(_onConfirmPasswordChanged);
  }

  void _onFullNameChanged() {
    if (_fullNameError != null) {
      setState(() {
        _fullNameError = _fullNameController.text.trim().isEmpty
            ? 'Nama lengkap wajib diisi.'
            : null;
      });
    }
  }

  void _onUsernameChanged() {
    if (_usernameError != null) {
      setState(() {
        _usernameError = _usernameController.text.trim().isEmpty
            ? 'Username wajib diisi.'
            : null;
      });
    }
  }

  void _onEmailChanged() {
    if (_emailError != null) {
      setState(() {
        _emailError = _validateEmail(
          _emailController.text.trim(),
        );
      });
    }
  }

  void _onPasswordChanged() {
    if (_passwordError != null) {
      setState(() {
        _passwordError = _validatePassword(
          _passwordController.text,
        );
      });
    }

    if (_confirmPasswordError != null) {
      setState(() {
        _confirmPasswordError = _validateConfirmPassword();
      });
    }
  }

  void _onConfirmPasswordChanged() {
    if (_confirmPasswordError != null) {
      setState(() {
        _confirmPasswordError = _validateConfirmPassword();
      });
    }
  }

  String? _validateEmail(String email) {
    if (email.isEmpty) {
      return 'Email wajib diisi.';
    }

    final emailRegex = RegExp(
      r'^[^@\s]+@[^@\s]+\.[^@\s]+$',
    );

    if (!emailRegex.hasMatch(email)) {
      return 'Masukkan alamat email yang valid.';
    }

    return null;
  }

  String? _validatePassword(String password) {
    if (password.isEmpty) {
      return 'Kata sandi wajib diisi.';
    }

    if (password.length < 8) {
      return 'Kata sandi minimal 8 karakter.';
    }

    return null;
  }

  String? _validateConfirmPassword() {
    final confirmPassword = _confirmPasswordController.text;

    if (confirmPassword.isEmpty) {
      return 'Konfirmasi kata sandi wajib diisi.';
    }

    if (confirmPassword != _passwordController.text) {
      return 'Kata sandi tidak sama.';
    }

    return null;
  }

  @override
  void dispose() {
    _fullNameController.removeListener(_onFullNameChanged);
    _usernameController.removeListener(_onUsernameChanged);
    _emailController.removeListener(_onEmailChanged);
    _passwordController.removeListener(_onPasswordChanged);
    _confirmPasswordController.removeListener(
      _onConfirmPasswordChanged,
    );

    _fullNameController.dispose();
    _usernameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _confirmPasswordController.dispose();

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

  Future<void> _register() async {
    FocusScope.of(context).unfocus();

    setState(() {
      _fullNameError = _fullNameController.text.trim().isEmpty
          ? 'Nama lengkap wajib diisi.'
          : null;

      _usernameError = _usernameController.text.trim().isEmpty
          ? 'Username wajib diisi.'
          : null;

      _emailError = _validateEmail(
        _emailController.text.trim(),
      );

      _passwordError = _validatePassword(
        _passwordController.text,
      );

      _confirmPasswordError = _validateConfirmPassword();
    });

    if (_fullNameError != null ||
        _usernameError != null ||
        _emailError != null ||
        _passwordError != null ||
        _confirmPasswordError != null) {
      return;
    }

    setState(() {
      _isLoading = true;
    });

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

      _showTanamiSnackBar(
        title: 'Registrasi Berhasil!',
        message: 'Akun kamu berhasil dibuat. Silakan masuk.',
        isSuccess: true,
      );

      Navigator.pushReplacementNamed(context, '/login');
    } catch (e) {
      if (!mounted) return;

      _showTanamiSnackBar(
        title: 'Registrasi Gagal',
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
                                  'Selamat Datang!',
                                  textAlign: TextAlign.center,
                                  style: TextStyle(
                                    fontFamily: 'Alexandria',
                                    fontSize: 22,
                                    fontWeight: FontWeight.w700,
                                    color: AppColors.darkGreen,
                                  ),
                                ),
                              ),

                              const SizedBox(height: 35),

                              AuthTextField(
                                label: 'Nama Lengkap',
                                hint: 'Masukan nama lengkap',
                                iconAsset:
                                    'assets/icons/person_outline.svg',
                                controller: _fullNameController,
                                errorText: _fullNameError,
                              ),

                              const SizedBox(height: 16),

                              AuthTextField(
                                label: 'Username',
                                hint: 'Buat nama pengguna',
                                iconAsset: 'assets/icons/person.svg',
                                controller: _usernameController,
                                errorText: _usernameError,
                              ),

                              const SizedBox(height: 16),

                              AuthTextField(
                                label: 'Email',
                                hint: 'Masukan alamat email',
                                iconAsset: 'assets/icons/email.svg',
                                controller: _emailController,
                                keyboardType:
                                    TextInputType.emailAddress,
                                errorText: _emailError,
                              ),

                              const SizedBox(height: 16),

                              AuthTextField(
                                label: 'Kata Sandi',
                                hint: 'Buat kata sandi',
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

                              const SizedBox(height: 16),

                              AuthTextField(
                                label: 'Konfirmasi Kata Sandi',
                                hint: 'Masukan ulang kata sandi',
                                iconAsset: 'assets/icons/lock.svg',
                                controller: _confirmPasswordController,
                                isPassword: true,
                                obscureText: _obscureConfirmPassword,
                                errorText: _confirmPasswordError,
                                onTogglePassword: () {
                                  setState(() {
                                    _obscureConfirmPassword =
                                        !_obscureConfirmPassword;
                                  });
                                },
                              ),
                            ],
                          ),
                        ),
                      ),

                      // AREA BAWAH
                      AuthButton(
                        text: _isLoading ? 'Memproses...' : 'Daftar',
                        onPressed: _isLoading ? null : _register,
                      ),

                      const SizedBox(height: 12),

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
                                color: AppColors.mediumGreen,
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
