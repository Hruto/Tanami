
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import '../../../core/constant/app_colors.dart';
import '../../../../core/api/api_config.dart';

/// Kartu tanaman khusus halaman Garden.
class GardenPlantCard extends StatelessWidget {
  final String name;
  final String location;
  final String harvest;
  final bool? healthy;
  final String iconAsset;
  final String? imageUrl;
  final VoidCallback? onTap;
  final int? maturity;

  const GardenPlantCard({
    super.key,
    required this.name,
    required this.location,
    required this.harvest,
    required this.healthy,
    required this.iconAsset,
    this.imageUrl,
    this.onTap,
    this.maturity,
  });

  Widget _buildPlantPlaceholder() => Center(
    child: SvgPicture.asset(
      iconAsset,
      width: 48,
      height: 48,
      colorFilter: const ColorFilter.mode(
        AppColors.mediumGreen, BlendMode.srcIn,
      ),
      fit: BoxFit.contain,
    ),
  );

  String? _resolveImageUrl(String? path) {
    if (path == null || path.trim().isEmpty) return null;
    final imageUri = Uri.parse(path);
    if (imageUri.hasScheme) return path;
    final apiUri = Uri.parse(ApiConfig.baseUrl);
    final backendUri = apiUri.replace(path: '', query: null, fragment: null);
    return backendUri.resolve(path).toString();
  }

  @override
  Widget build(BuildContext context) {
    final resolvedImageUrl = _resolveImageUrl(imageUrl);
    final statusText = healthy == null
        ? 'Belum terdeteksi'
        : healthy!
            ? 'Sehat'
            : 'Sakit';
    final statusColor = healthy == null
        ? AppColors.grey
        : healthy!
            ? AppColors.mediumGreen
            : AppColors.red;

    return Material(
      color: AppColors.background,
      borderRadius: BorderRadius.circular(20),
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(20),
        child: Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: AppColors.background,
            borderRadius: BorderRadius.circular(20),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.12),
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
                child: resolvedImageUrl != null
                    ? Image.network(
                        resolvedImageUrl,
                        fit: BoxFit.cover,
                        loadingBuilder: (context, child, progress) {
                          if (progress == null) return child;
                          return const Center(
                            child: SizedBox(
                              width: 20,
                              height: 20,
                              child: CircularProgressIndicator(
                                strokeWidth: 2,
                                color: AppColors.mediumGreen,
                              ),
                            ),
                          );
                        },
                        errorBuilder: (context, error, stackTrace) {
                          debugPrint('Gagal memuat foto: $resolvedImageUrl');
                          debugPrint('Error: $error');
                          return _buildPlantPlaceholder();
                        },
                      )
                    : _buildPlantPlaceholder(),
              ),
              const SizedBox(width: 12),

              // Informasi tanaman
              Expanded(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      name,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: 'Alexandria',
                        fontSize: 13,
                        fontWeight: FontWeight.w700,
                        color: AppColors.darkGreen,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Row(
                      children: [
                        SvgPicture.asset(
                          'assets/icons/placement.svg',
                          width: 14,
                          height: 14,
                          colorFilter: const ColorFilter.mode(
                            AppColors.mediumGreen, BlendMode.srcIn,
                          ),
                        ),
                        const SizedBox(width: 4),
                        Expanded(
                          child: Text(
                            location,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              fontFamily: 'Alexandria',
                              fontSize: 10,
                              color: AppColors.grey,
                            ),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 7),

                    // Status kesehatan
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 10, vertical: 3,
                      ),
                      decoration: BoxDecoration(
                        color: statusColor,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        statusText,
                        style: const TextStyle(
                          fontFamily: 'Alexandria',
                          color: Colors.white,
                          fontSize: 9,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                    const SizedBox(height: 3),

                    // Estimasi panen
                    Text(
                      harvest,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: const TextStyle(
                        fontFamily: 'Alexandria',
                        fontSize: 9,
                        color: AppColors.grey,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 5),
              const Icon(
                Icons.chevron_right_rounded,
                size: 27,
                color: AppColors.grey,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
