
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';

// Icon assets
const String gardenNameIcon = 'assets/icons/Pencil.svg';
const String gardenPlantTypeIcon = 'assets/icons/tree_Palm.svg';
const String gardenCalendarIcon = 'assets/icons/calendar.svg';

const String _fontFamily = 'Alexandria';

const TextStyle _fieldValueStyle = TextStyle(
  fontFamily: _fontFamily,
  fontSize: 14,
  fontWeight: FontWeight.w600,
  color: AppColors.mediumGreen,
);

const TextStyle _fieldHintStyle = TextStyle(
  fontFamily: _fontFamily,
  fontSize: 14,
  fontWeight: FontWeight.w500,
  color: AppColors.mediumGreen,
);

const TextStyle _errorStyle = TextStyle(
  fontFamily: _fontFamily,
  fontSize: 11,
  fontWeight: FontWeight.w500,
  color: AppColors.red,
);

// SVG icon helper
Widget _buildSvgIcon(
  String asset, {
  double size = 21,
}) {
  return SvgPicture.asset(
    asset,
    width: size,
    height: size,
    fit: BoxFit.contain,
    errorBuilder: (context, error, stackTrace) {
      debugPrint('SVG ERROR: $asset');
      debugPrint('$error');

      return Icon(
        Icons.error_outline_rounded,
        color: AppColors.red,
        size: size,
      );
    },
  );
}

// Nama dan jenis tanaman
class GardenTextField extends StatelessWidget {
  final TextEditingController controller;
  final String label;
  final String hint;
  final String iconAsset;
  final TextInputType keyboardType;
  final String? errorText;
  final ValueChanged<String>? onChanged;

  const GardenTextField({
    super.key,
    required this.controller,
    required this.label,
    required this.hint,
    required this.iconAsset,
    this.keyboardType = TextInputType.text,
    this.errorText,
    this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _GardenFieldLabel(label: label),
        const SizedBox(height: 7),
        TextField(
          controller: controller,
          keyboardType: keyboardType,
          onChanged: onChanged,
          style: _fieldValueStyle,
          cursorColor: AppColors.mediumGreen,
          decoration: _fieldDecoration(
            hint: hint,
            iconAsset: iconAsset,
          ),
        ),
        if (errorText != null) ...[
          const SizedBox(height: 6),
          _FieldError(message: errorText!),
        ],
      ],
    );
  }
}

// Field tanggal
class GardenDateField extends StatelessWidget {
  final String label;
  final String iconAsset;
  final String value;
  final bool isPlaceholder;
  final VoidCallback onTap;
  final String? errorText;

  const GardenDateField({
    super.key,
    required this.label,
    required this.iconAsset,
    required this.value,
    required this.isPlaceholder,
    required this.onTap,
    this.errorText,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _GardenFieldLabel(label: label),
        const SizedBox(height: 7),
        Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            borderRadius: BorderRadius.circular(20),
            child: Container(
              height: 50,
              padding: const EdgeInsets.symmetric(horizontal: 15),
              decoration: BoxDecoration(
                color: AppColors.fieldBackground,
                borderRadius: BorderRadius.circular(20),
              ),
              child: Row(
                children: [
                  _buildSvgIcon(
                    iconAsset,
                    size: 21,
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Text(
                      value,
                      style: isPlaceholder
                          ? _fieldHintStyle
                          : _fieldValueStyle,
                    ),
                  ),
                  const Icon(
                    Icons.keyboard_arrow_down_rounded,
                    color: AppColors.mediumGreen,
                    size: 23,
                  ),
                ],
              ),
            ),
          ),
        ),
        if (errorText != null) ...[
          const SizedBox(height: 6),
          _FieldError(message: errorText!),
        ],
      ],
    );
  }
}

// Dropdown field
class GardenDropdownField extends StatelessWidget {
  final String label;
  final String value;
  final List<DropdownMenuItem<String>> items;
  final ValueChanged<String?> onChanged;

  const GardenDropdownField({
    super.key,
    required this.label,
    required this.value,
    required this.items,
    required this.onChanged,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        _GardenFieldLabel(label: label),
        const SizedBox(height: 7),
        Container(
          height: 50,
          padding: const EdgeInsets.symmetric(horizontal: 15),
          decoration: BoxDecoration(
            color: AppColors.fieldBackground,
            borderRadius: BorderRadius.circular(20),
          ),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              value: value,
              isExpanded: true,
              dropdownColor: AppColors.fieldBackground,
              borderRadius: BorderRadius.circular(16),
              icon: const Icon(
                Icons.keyboard_arrow_down_rounded,
                color: AppColors.mediumGreen,
                size: 23,
              ),
              style: _fieldValueStyle,
              items: items,
              onChanged: onChanged,
            ),
          ),
        ),
      ],
    );
  }
}

// Label field
class _GardenFieldLabel extends StatelessWidget {
  final String label;

  const _GardenFieldLabel({
    required this.label,
  });

  @override
  Widget build(BuildContext context) {
    return Text(
      label,
      style: const TextStyle(
        fontFamily: _fontFamily,
        fontSize: 13,
        fontWeight: FontWeight.w700,
        color: AppColors.textSecondary,
      ),
    );
  }
}

// Error message
class _FieldError extends StatelessWidget {
  final String message;

  const _FieldError({
    required this.message,
  });

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Icon(
          Icons.error_outline_rounded,
          color: AppColors.red,
          size: 13,
        ),
        const SizedBox(width: 5),
        Expanded(
          child: Text(
            message,
            style: _errorStyle,
          ),
        ),
      ],
    );
  }
}

// TextField decoration
InputDecoration _fieldDecoration({
  required String hint,
  required String iconAsset,
}) {
  return InputDecoration(
    hintText: hint,
    filled: true,
    fillColor: AppColors.fieldBackground,
    contentPadding: const EdgeInsets.symmetric(
      horizontal: 14,
      vertical: 14,
    ),
    prefixIcon: Padding(
      padding: const EdgeInsets.all(14),
      child: _buildSvgIcon(
        iconAsset,
        size: 21,
      ),
    ),
    hintStyle: _fieldHintStyle,
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
      borderSide: BorderSide.none,
    ),
  );
}
