
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

class AuthTextField extends StatelessWidget {
  final String label;
  final String hint;
  final String iconAsset;
  final TextEditingController controller;
  final bool isPassword;
  final bool obscureText;
  final VoidCallback? onTogglePassword;
  final TextInputType keyboardType;
  final String? errorText;

  const AuthTextField({
    super.key,
    required this.label,
    required this.hint,
    required this.iconAsset,
    required this.controller,
    this.isPassword = false,
    this.obscureText = false,
    this.onTogglePassword,
    this.keyboardType = TextInputType.text,
    this.errorText,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: const TextStyle(
            fontSize: 14,
            fontWeight: FontWeight.w700,
            color: Color(0xFF344236),
            fontFamily: 'Alexandria',
          ),
        ),

        const SizedBox(height: 8),

        TextField(
          controller: controller,
          keyboardType: keyboardType,
          obscureText: isPassword && obscureText,
          style: const TextStyle(
            fontSize: 14,
            color: Color(0xFF6B8F70),
            fontWeight: FontWeight.w600,
            fontFamily: 'Alexandria',
          ),
          decoration: InputDecoration(
            hintText: hint,
            hintStyle: const TextStyle(
              fontSize: 14,
              color: Color(0xFF6B8F70),
              fontWeight: FontWeight.w600,
              fontFamily: 'Alexandria',
            ),

            // Prefix SVG Icon
            prefixIcon: Padding(
              padding: const EdgeInsets.all(14),
              child: SvgPicture.asset(
                iconAsset,
                width: 20,
                height: 20,
                fit: BoxFit.contain,
                colorFilter: const ColorFilter.mode(
                  Color(0xFF6B8F70),
                  BlendMode.srcIn,
                ),
              ),
            ),

            // Password Visibility Toggle
            suffixIcon: isPassword
                ? IconButton(
                    onPressed: onTogglePassword,
                    icon: SvgPicture.asset(
                      'assets/icons/hide_pass.svg',
                      width: 21,
                      height: 21,
                      fit: BoxFit.contain,
                      colorFilter: const ColorFilter.mode(
                        Color(0xFF6B8F70),
                        BlendMode.srcIn,
                      ),
                    ),
                  )
                : null,

            filled: true,
            fillColor: const Color(0xFFDDE3D9),

            contentPadding: const EdgeInsets.symmetric(
              vertical: 14,
              horizontal: 16,
            ),

            errorText: errorText,
            errorStyle: const TextStyle(
              fontFamily: 'Alexandria',
              fontSize: 10,
              color: Color(0xFFC65B52),
            ),

            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: BorderSide.none,
            ),

            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: BorderSide.none,
            ),

            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: const BorderSide(
                color: Color(0xFF6B8F70),
                width: 1,
              ),
            ),

            errorBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: const BorderSide(
                color: Color(0xFFC65B52),
                width: 1,
              ),
            ),

            focusedErrorBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: const BorderSide(
                color: Color(0xFFC65B52),
                width: 1,
              ),
            ),
          ),
        ),
      ],
    );
  }
}
