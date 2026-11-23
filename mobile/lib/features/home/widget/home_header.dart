
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';

class HomeHeader extends StatelessWidget {
  final String userName;

  const HomeHeader({
    super.key,
    required this.userName,
  });

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.only(top: 18),
          child: Center(
            child: SvgPicture.asset(
              'assets/images/logo_header.svg',
              width: 28,
              height: 28,
            ),
          ),
        ),
        const SizedBox(height: 28),
        Row(
          children: [
            const CircleAvatar(
              radius: 25,
              backgroundColor: AppColors.lightGreen,
              child: Icon(
                Icons.person,
                size: 30,
                color: AppColors.mediumGreen,
              ),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Halo, Selamat Datang!',
                    style: TextStyle(
                      color: Colors.white70,
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    userName.isNotEmpty ? userName : 'Pengguna',
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 21,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ),
            ),
            IconButton(
              onPressed: () {},
              icon: const Icon(
                Icons.notifications_none_rounded,
                color: Colors.white,
                size: 29,
              ),
            ),
          ],
        ),
      ],
    );
  }
}
