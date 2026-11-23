
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../core/constant/app_colors.dart';

class BottomNavBar extends StatelessWidget {
  final int currentIndex;
  final ValueChanged<int> onTap;

  const BottomNavBar({
    super.key,
    required this.currentIndex,
    required this.onTap,
  });

  static const Color green = AppColors.mediumGreen;
  static const Color muted = AppColors.grey;

  static const List<String> icons = [
    'assets/icons/home_outline.svg',
    'assets/icons/tree_outline.svg',
    'assets/icons/history_outline.svg',
    'assets/icons/chat_outline.svg',
    'assets/icons/person_outline.svg',
  ];

  static const List<String> selectedIcons = [
    'assets/icons/home_filled.svg',
    'assets/icons/tree_filled.svg',
    'assets/icons/history_filled.svg',
    'assets/icons/chat_filled.svg',
    'assets/icons/person_filled.svg',
  ];

  static const List<String> labels = [
    'Beranda',
    'Kebun',
    'Riwayat',
    'Forum',
    'Profil',
  ];

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      top: false,
      child: Container(
        margin: const EdgeInsets.fromLTRB(16, 0, 16, 12),
        padding: const EdgeInsets.symmetric(
          vertical: 12,
          horizontal: 8,
        ),
        decoration: BoxDecoration(
          color: AppColors.background,
          borderRadius: BorderRadius.circular(40),
          boxShadow: [
            BoxShadow(
              color: Colors.black.withOpacity(0.14),
              blurRadius: 14,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Row(
          children: List.generate(icons.length, (index) {
            final selected = currentIndex == index;
            final itemColor = selected ? green : muted;

            return Expanded(
              child: InkWell(
                onTap: () => onTap(index),
                borderRadius: BorderRadius.circular(20),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    SvgPicture.asset(
                      selected
                          ? selectedIcons[index]
                          : icons[index],
                      width: 24,
                      height: 24,
                    ),
                    const SizedBox(height: 4),
                    Text(
                      labels[index],
                      style: TextStyle(
                        fontSize: 11,
                        color: itemColor,
                        fontWeight: selected
                            ? FontWeight.w700
                            : FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              ),
            );
          }),
        ),
      ),
    );
  }
}
