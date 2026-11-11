
import 'package:flutter/material.dart';

class AuthTextField extends StatelessWidget {
  final String label;
  final String hint;
  final IconData icon;
  final TextEditingController controller;
  final bool isPassword;
  final bool obscureText;
  final VoidCallback? onTogglePassword;
  final TextInputType keyboardType;

  const AuthTextField({
    super.key,
    required this.label,
    required this.hint,
    required this.icon,
    required this.controller,
    this.isPassword = false,
    this.obscureText = false,
    this.onTogglePassword,
    this.keyboardType = TextInputType.text,
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
          ),
        ),
        const SizedBox(height: 8),
        SizedBox(
          height: 50,
          child: TextField(
            controller: controller,
            keyboardType: keyboardType,
            obscureText: isPassword && obscureText,
            style: const TextStyle(
              fontSize: 14,
              color: Color(0xFF6B8F70),
              fontWeight: FontWeight.w600,
            ),
            decoration: InputDecoration(
              hintText: hint,
              hintStyle: const TextStyle(
                fontSize: 14,
                color: Color(0xFF6B8F70),
                fontWeight: FontWeight.w600,
              ),
              prefixIcon: Icon(
                icon,
                color: const Color(0xFF6B8F70),
                size: 23,
              ),
              suffixIcon: isPassword
                  ? IconButton(
                      onPressed: onTogglePassword,
                      icon: Icon(
                        obscureText
                            ? Icons.visibility_off_outlined
                            : Icons.visibility_outlined,
                        color: const Color(0xFF6B8F70),
                        size: 21,
                      ),
                    )
                  : null,
              filled: true,
              fillColor: const Color(0xFFDDE3D9),
              contentPadding: const EdgeInsets.symmetric(
                vertical: 14,
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
            ),
          ),
        ),
      ],
    );
  }
}
