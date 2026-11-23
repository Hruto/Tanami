
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../constant/app_colors.dart';

class HarvestPlantCard extends StatelessWidget {
  final String name;
  final String location;
  final String harvest;
  final int? maturity;
  final bool healthy;
  final String iconAsset;
  final String? imageUrl;

  const HarvestPlantCard({
    super.key,
    required this.name,
    required this.location,
    required this.harvest,
    this.maturity,
    required this.healthy,
    required this.iconAsset,
    this.imageUrl,
  });

  Widget _buildPlantPlaceholder() {
    return Center(
      child: SvgPicture.asset(
        iconAsset,
        width: 48,
        height: 48,
        colorFilter: const ColorFilter.mode(
          AppColors.mediumGreen,
          BlendMode.srcIn,
        ),
        fit: BoxFit.contain,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final progress = maturity?.clamp(0, 100);

    return Container(
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withValues(alpha: 0.14),
            blurRadius: 7,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        children: [
          // Foto tanaman
          Container(
            width: 80,
            height: 80,
            decoration: BoxDecoration(
              color: AppColors.lightGreen,
              borderRadius: BorderRadius.circular(12),
            ),
            clipBehavior: Clip.antiAlias,
            child: imageUrl != null && imageUrl!.isNotEmpty
                ? Image.network(
                    imageUrl!,
                    fit: BoxFit.cover,
                    errorBuilder: (context, error, stackTrace) {
                      return _buildPlantPlaceholder();
                    },
                  )
                : _buildPlantPlaceholder(),
          ),

          const SizedBox(width: 12),

          // Informasi tanaman
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  name,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    color: AppColors.darkGreen,
                  ),
                ),

                const SizedBox(height: 3),

                Row(
                  children: [
                    const Icon(
                      Icons.location_on_outlined,
                      size: 13,
                      color: AppColors.grey,
                    ),
                    const SizedBox(width: 4),
                    Expanded(
                      child: Text(
                        location,
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                          fontSize: 10,
                          color: AppColors.grey,
                        ),
                      ),
                    ),
                  ],
                ),

                const SizedBox(height: 9),

                // Status kesehatan
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 3,
                  ),
                  decoration: BoxDecoration(
                    color: healthy
                        ? AppColors.mediumGreen
                        : AppColors.red,
                    borderRadius: BorderRadius.circular(5),
                  ),
                  child: Text(
                    healthy ? 'Sehat' : 'Sakit',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 10,
                    ),
                  ),
                ),

                const SizedBox(height: 3),

                // Estimasi panen
                Text(
                  harvest,
                  style: const TextStyle(
                    fontSize: 10,
                    color: AppColors.grey,
                  ),
                ),
              ],
            ),
          ),

          const SizedBox(width: 5),

          // Indikator kematangan
          Column(
            children: [
              const Text(
                'Kematangan',
                style: TextStyle(
                  fontSize: 9,
                  color: AppColors.darkGreen,
                ),
              ),

              const SizedBox(height: 7),

              SizedBox(
                width: 58,
                height: 58,
                child: Stack(
                  alignment: Alignment.center,
                  children: [
                    CircularProgressIndicator(
                      value: progress == null
                          ? 0
                          : progress / 100,
                      strokeWidth: 8,
                      backgroundColor: AppColors.lightGreen,
                      valueColor:
                          const AlwaysStoppedAnimation<Color>(
                        AppColors.orange,
                      ),
                    ),

                    Text(
                      progress == null ? '--' : '$progress%',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                        color: AppColors.darkGreen,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
