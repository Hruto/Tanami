
import 'package:flutter/material.dart';

import '../../../core/constant/app_colors.dart';
import '../models/plant_summary_model.dart';
import '../services/plant_summary_service.dart';

class PlantSummaryCard extends StatefulWidget {
  final String? farmId;

  const PlantSummaryCard({
    super.key,
    this.farmId,
  });

  @override
  State<PlantSummaryCard> createState() => _PlantSummaryCardState();
}

class _PlantSummaryCardState extends State<PlantSummaryCard> {
  final PlantSummaryService _summaryService = PlantSummaryService();

  late Future<PlantSummaryModel?> _summaryFuture;

  @override
  void initState() {
    super.initState();
    _summaryFuture = _loadSummary();
  }


@override
void didUpdateWidget(covariant PlantSummaryCard oldWidget) {
  super.didUpdateWidget(oldWidget);

  if (oldWidget.farmId != widget.farmId) {
    setState(() {
      _summaryFuture = _loadSummary();
    });
  }
}


  Future<PlantSummaryModel?> _loadSummary() async {
    if (widget.farmId == null) return null;

    return _summaryService.getPlantSummary(widget.farmId!);
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<PlantSummaryModel?>(
      future: _summaryFuture,
      builder: (context, snapshot) {
        if (widget.farmId == null) {
          return _buildEmptyState(
            'Tambahkan kebun untuk melihat ringkasan tanaman.',
          );
        }

        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildLoading();
        }

        if (snapshot.hasError) {
          return _buildEmptyState(
            'Gagal memuat ringkasan tanaman.',
          );
        }

        final summary = snapshot.data;

        if (summary == null || summary.total == 0) {
          return _buildEmptyState(
            'Belum ada tanaman di kebun ini.',
          );
        }

        return Row(
          children: [
            Expanded(
              child: _SummaryItem(
                title: 'Tanaman Sehat',
                amount: summary.healthy.toString(),
                total: summary.total.toString(),
                percent: summary.healthyPercent,
                color: AppColors.mediumGreen,
              ),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: _SummaryItem(
                title: 'Tanaman Sakit',
                amount: summary.sick.toString(),
                total: summary.total.toString(),
                percent: summary.sickPercent,
                color: AppColors.red,
              ),
            ),
          ],
        );
      },
    );
  }

  Widget _buildLoading() {
    return Container(
      height: 90,
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(20),
      ),
      child: const Center(
        child: CircularProgressIndicator(
          color: AppColors.mediumGreen,
        ),
      ),
    );
  }

  Widget _buildEmptyState(String message) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(
        horizontal: 16,
        vertical: 20,
      ),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Text(
        message,
        textAlign: TextAlign.center,
        style: const TextStyle(
          fontSize: 12,
          color: AppColors.grey,
        ),
      ),
    );
  }
}

class _SummaryItem extends StatelessWidget {
  final String title;
  final String amount;
  final String total;
  final int percent;
  final Color color;

  const _SummaryItem({
    required this.title,
    required this.amount,
    required this.total,
    required this.percent,
    required this.color,
  });

  @override
  Widget build(BuildContext context) {
    final progress = percent.clamp(0, 100);

    return Container(
      padding: const EdgeInsets.symmetric(
        horizontal: 12,
        vertical: 10,
      ),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.13),
            blurRadius: 7,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(
                    fontSize: 11,
                    color: AppColors.grey,
                  ),
                ),
                const SizedBox(height: 2),
                RichText(
                  text: TextSpan(
                    children: [
                      TextSpan(
                        text: amount,
                        style: TextStyle(
                          fontSize: 28,
                          fontWeight: FontWeight.w800,
                          color: color,
                        ),
                      ),
                      TextSpan(
                        text: '/$total',
                        style: const TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w700,
                          color: AppColors.darkGreen,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          SizedBox(
            width: 44,
            height: 44,
            child: Stack(
              alignment: Alignment.center,
              children: [
                CircularProgressIndicator(
                  value: progress / 100,
                  strokeWidth: 6,
                  backgroundColor: AppColors.lightGreen,
                  valueColor: AlwaysStoppedAnimation<Color>(color),
                ),
                Text(
                  '$progress%',
                  style: const TextStyle(
                    fontSize: 10,
                    fontWeight: FontWeight.w600,
                    color: AppColors.darkGreen,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
