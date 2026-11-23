
import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/constant/app_colors.dart';
import '../models/weather_model.dart';
import '../services/weather_service.dart';

// Konfigurasi tampilan berdasarkan kondisi cuaca
class _WeatherStyle {
  final List<Color> colors;
  final IconData icon;

  const _WeatherStyle({
    required this.colors,
    required this.icon,
  });
}

class WeatherCard extends StatefulWidget {
  final String? farmId;
  final String? location;

  const WeatherCard({
    super.key,
    this.farmId,
    this.location,
  });

  @override
  State<WeatherCard> createState() => _WeatherCardState();
}

class _WeatherCardState extends State<WeatherCard> {
  final WeatherService _weatherService = WeatherService();

  late Future<WeatherModel?> _weatherFuture;

  @override
  void initState() {
    super.initState();
    _weatherFuture = _loadWeather();
  }

@override
void didUpdateWidget(covariant WeatherCard oldWidget) {
  super.didUpdateWidget(oldWidget);

  if (oldWidget.farmId != widget.farmId) {
    _weatherFuture = _loadWeather();
  }
}


  Future<WeatherModel?> _loadWeather() async {
    if (widget.farmId == null) return null;

    return _weatherService.getWeather(widget.farmId!);
  }

  // Mengenali kondisi cuaca dari response API
  _WeatherStyle _getWeatherStyle(String description) {
    final condition = description.toLowerCase().trim();

    // 1. Bersalju
    if (condition.contains('salju') ||
        condition.contains('snow')) {
      return const _WeatherStyle(
        colors: [
          AppColors.weatherSnowyLight,
          AppColors.weatherSnowyDark,
        ],
        icon: Icons.ac_unit,
      );
    }

    // 2. Hujan
    if (condition.contains('hujan') ||
        condition.contains('rain') ||
        condition.contains('drizzle') ||
        condition.contains('gerimis') ||
        condition.contains('shower') ||
        condition.contains('thunderstorm') ||
        condition.contains('badai')) {
      return const _WeatherStyle(
        colors: [
          AppColors.weatherRainyLight,
          AppColors.weatherRainyDark,
        ],
        icon: Icons.cloudy_snowing,
      );
    }

    // 3. Berkabut
    if (condition.contains('kabut') ||
        condition.contains('fog') ||
        condition.contains('mist') ||
        condition.contains('haze')) {
      return const _WeatherStyle(
        colors: [
          AppColors.weatherFoggyLight,
          AppColors.weatherFoggyDark,
        ],
        icon: Icons.cloud,
      );
    }

    // 4. Berangin
    if (condition.contains('angin') ||
        condition.contains('wind')) {
      return const _WeatherStyle(
        colors: [
          AppColors.weatherWindyLight,
          AppColors.weatherWindyDark,
        ],
        icon: Icons.air,
      );
    }

    // 5. Berawan
    if (condition.contains('awan') ||
        condition.contains('cloud') ||
        condition.contains('overcast')) {
      return const _WeatherStyle(
        colors: [
          AppColors.weatherCloudyLight,
          AppColors.weatherCloudyDark,
        ],
        icon: Icons.cloud,
      );
    }

    // 6. Cerah (default)
    return const _WeatherStyle(
      colors: [
        AppColors.weatherSunnyLight,
        AppColors.weatherSunnyDark,
      ],
      icon: Icons.wb_sunny_rounded,
    );
  }

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<WeatherModel?>(
      future: _weatherFuture,
      builder: (context, snapshot) {
        if (widget.farmId == null) {
          return _buildNoWeatherData();
        }

        if (snapshot.connectionState == ConnectionState.waiting) {
          return _buildWeatherLoading();
        }

        if (snapshot.hasError) {
          return _buildWeatherError();
        }

        final weather = snapshot.data;
        final current = weather?.currentSlot;

        if (current == null) {
          return _buildNoWeatherData();
        }

        return _buildWeatherContent(
          temperature: current.temperature,
          description: current.weatherDescription,
          location: widget.location ?? '-',
          dateTime: current.dateTime,
        );
      },
    );
  }

  // Kartu utama cuaca
  Widget _buildWeatherContent({
    required double? temperature,
    required String description,
    required String location,
    required DateTime dateTime,
  }) {
    final weatherStyle = _getWeatherStyle(description);

    return Container(
      margin: const EdgeInsets.symmetric(
        horizontal: 20,
        vertical: 12,
      ),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(20),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.10),
            blurRadius: 7,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          // Bagian ilustrasi dan informasi cuaca
          SizedBox(
            height: 150,
            width: double.infinity,
            child: Stack(
              children: [
                // Background gradient dinamis
                Container(
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: weatherStyle.colors,
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                  ),
                ),

                // Dekorasi landscape sederhana
                Positioned.fill(
                  child: CustomPaint(
                    painter: _WeatherLandscapePainter(
                      condition: description,
                      colors: weatherStyle.colors,
                    ),
                  ),
                ),

                // Informasi suhu, kondisi, dan lokasi
                Positioned(
                  top: 18,
                  left: 20,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            temperature == null
                                ? '--°'
                                : '${temperature.round()}°',
                            style: const TextStyle(
                              fontSize: 42,
                              fontWeight: FontWeight.bold,
                              color: Colors.white,
                            ),
                          ),
                        ],
                      ),

                      const SizedBox(height: 2),

                      Text(
                        description,
                        style: const TextStyle(
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                          color: Colors.white,
                        ),
                      ),

                      const SizedBox(height: 5),

                      Row(
                        children: [
                          const Icon(
                            Icons.location_on_outlined,
                            color: Colors.white,
                            size: 15,
                          ),
                          const SizedBox(width: 3),
                          Text(
                            location,
                            style: const TextStyle(
                              fontSize: 12,
                              color: Colors.white,
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),

                // Ikon kondisi cuaca
                Positioned(
                  top: 20,
                  right: 25,
                  child: Icon(
                    weatherStyle.icon,
                    size: 60,
                    color: Colors.white.withOpacity(0.9),
                  ),
                ),
              ],
            ),
          ),

          // Bagian waktu dan tanggal
          Padding(
            padding: const EdgeInsets.symmetric(
              horizontal: 18,
              vertical: 14,
            ),
            child: Row(
              children: [
                const Icon(
                  Icons.access_time_rounded,
                  size: 16,
                  color: AppColors.grey,
                ),

                const SizedBox(width: 6),

                Text(
                  _formatTime(dateTime),
                  style: const TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: AppColors.navy,
                  ),
                ),

                const Spacer(),

                Text(
                  _formatDate(dateTime),
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.grey,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  // Tampilan ketika belum ada data cuaca
  Widget _buildNoWeatherData() {
    return Container(
      width: double.infinity,
      height: 250,
      margin: const EdgeInsets.symmetric(
        horizontal: 20,
        vertical: 12,
      ),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(22),
      ),
      clipBehavior: Clip.antiAlias,
      child: Column(
        children: [
          Expanded(
            child: Stack(
              children: [
                // Background dan ilustrasi
                Positioned.fill(
                  child: CustomPaint(
                    painter: _UnknownWeatherPainter(),
                  ),
                ),

                // Tanda tanya
                Center(
                  child: Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: Text(
                      '?',
                      style: TextStyle(
                        fontSize: 105,
                        height: 1,
                        fontWeight: FontWeight.w800,
                        color: Colors.grey.shade500,
                      ),
                    ),
                  ),
                ),

                // Label tidak diketahui
                Positioned(
                  bottom: 7,
                  left: 0,
                  right: 0,
                  child: Center(
                    child: Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 28,
                        vertical: 4,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(30),
                        border: Border.all(
                          color: const Color(0xFFD0D2D4),
                          width: 1,
                        ),
                      ),
                      child: const Text(
                        'tidak diketahui',
                        style: TextStyle(
                          fontSize: 11,
                          color: Color(0xFF999CA0),
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          ),

          // Bagian bawah kartu
          Container(
            height: 60,
            width: double.infinity,
            color: Colors.white,
          ),
        ],
      ),
    );
  }

  // Loading
  Widget _buildWeatherLoading() {
    return Container(
      margin: const EdgeInsets.symmetric(
        horizontal: 20,
        vertical: 12,
      ),
      padding: const EdgeInsets.all(28),
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

  // Error
  Widget _buildWeatherError() {
    return _buildMessageCard(
      icon: Icons.wifi_off_rounded,
      title: 'Gagal memuat cuaca',
      subtitle: 'Periksa koneksi atau coba muat ulang halaman.',
    );
  }

  // Komponen pesan
  Widget _buildMessageCard({
    required IconData icon,
    required String title,
    required String subtitle,
  }) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(
        horizontal: 20,
        vertical: 12,
      ),
      padding: const EdgeInsets.symmetric(
        horizontal: 20,
        vertical: 24,
      ),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(20),
      ),
      child: Column(
        children: [
          Icon(
            icon,
            size: 35,
            color: AppColors.grey,
          ),

          const SizedBox(height: 10),

          Text(
            title,
            style: const TextStyle(
              fontSize: 14,
              fontWeight: FontWeight.w600,
              color: AppColors.navy,
            ),
          ),

          const SizedBox(height: 5),

          Text(
            subtitle,
            textAlign: TextAlign.center,
            style: const TextStyle(
              fontSize: 12,
              color: AppColors.grey,
            ),
          ),
        ],
      ),
    );
  }

  // Format waktu
  String _formatTime(DateTime dateTime) {
    final hour = dateTime.hour.toString().padLeft(2, '0');
    final minute = dateTime.minute.toString().padLeft(2, '0');

    return '$hour:$minute';
  }

  // Format tanggal
  String _formatDate(DateTime dateTime) {
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr',
      'Mei', 'Jun', 'Jul', 'Agu',
      'Sep', 'Okt', 'Nov', 'Des',
    ];

    return '${dateTime.day} ${months[dateTime.month - 1]} ${dateTime.year}';
  }
}

// PAINTER UNTUK WEATHER TIDAK DIKETAHUI
class _UnknownWeatherPainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final width = size.width;
    final height = size.height;

    // Background
    final backgroundPaint = Paint()
      ..color = const Color(0xFFF8F8F8);

    canvas.drawRect(
      Offset.zero & size,
      backgroundPaint,
    );

    // Matahari
    final sunPaint = Paint()
      ..color = const Color(0xFFE1E2E4);

    final sunCenter = Offset(
      width * 0.59,
      height * 0.36,
    );

    canvas.drawCircle(
      sunCenter,
      22,
      sunPaint,
    );

    // Sinar matahari
    final rayPaint = Paint()
      ..color = const Color(0xFFC9CBCD)
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;

    for (int i = 0; i < 8; i++) {
      final angle = i * math.pi / 4;

      final start = Offset(
        sunCenter.dx + 29 * math.cos(angle),
        sunCenter.dy + 29 * math.sin(angle),
      );

      final end = Offset(
        sunCenter.dx + 37 * math.cos(angle),
        sunCenter.dy + 37 * math.sin(angle),
      );

      canvas.drawLine(
        start,
        end,
        rayPaint,
      );
    }

    // Awan kiri dan kanan
    final cloudPaint = Paint()
      ..color = const Color(0xFFE0E1E3);

    _drawCloud(
      canvas,
      Offset(width * 0.32, height * 0.60),
      19,
      cloudPaint,
    );

    _drawCloud(
      canvas,
      Offset(width * 0.68, height * 0.67),
      18,
      cloudPaint,
    );

    // Landscape
    final landscapePaint = Paint()
      ..color = const Color(0xFFE9EAEB);

    final landscapePath = Path()
      ..moveTo(0, height * 0.80)
      ..quadraticBezierTo(
        width * 0.12,
        height * 0.72,
        width * 0.24,
        height * 0.83,
      )
      ..quadraticBezierTo(
        width * 0.48,
        height * 0.91,
        width * 0.70,
        height * 0.82,
      )
      ..quadraticBezierTo(
        width * 0.88,
        height * 0.73,
        width,
        height * 0.82,
      )
      ..lineTo(width, height)
      ..lineTo(0, height)
      ..close();

    canvas.drawPath(
      landscapePath,
      landscapePaint,
    );

    // Garis tanah
    final groundPaint = Paint()
      ..color = const Color(0xFFD9DADB);

    canvas.drawRect(
      Rect.fromLTWH(
        0,
        height * 0.94,
        width,
        height * 0.06,
      ),
      groundPaint,
    );

    // Rumput kiri dan kanan
    final grassPaint = Paint()
      ..color = const Color(0xFFC9CBCC)
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round;

    _drawGrass(
      canvas,
      Offset(width * 0.09, height * 0.85),
      grassPaint,
    );

    _drawGrass(
      canvas,
      Offset(width * 0.92, height * 0.85),
      grassPaint,
    );

    // Batu kecil
    final stonePaint = Paint()
      ..color = const Color(0xFFC9CBCC);

    canvas.drawCircle(
      Offset(width * 0.26, height * 0.91),
      9,
      stonePaint,
    );

    canvas.drawCircle(
      Offset(width * 0.81, height * 0.91),
      9,
      stonePaint,
    );
  }

  void _drawCloud(
    Canvas canvas,
    Offset center,
    double radius,
    Paint paint,
  ) {
    final path = Path()
      ..addOval(
        Rect.fromCircle(
          center: Offset(
            center.dx - radius * 0.55,
            center.dy,
          ),
          radius: radius * 0.65,
        ),
      )
      ..addOval(
        Rect.fromCircle(
          center: Offset(
            center.dx,
            center.dy - radius * 0.25,
          ),
          radius: radius,
        ),
      )
      ..addOval(
        Rect.fromCircle(
          center: Offset(
            center.dx + radius * 0.65,
            center.dy,
          ),
          radius: radius * 0.7,
        ),
      );

    canvas.drawPath(path, paint);
  }

  void _drawGrass(
    Canvas canvas,
    Offset base,
    Paint paint,
  ) {
    canvas.drawLine(
      base,
      Offset(base.dx - 9, base.dy - 15),
      paint,
    );

    canvas.drawLine(
      base,
      Offset(base.dx, base.dy - 20),
      paint,
    );

    canvas.drawLine(
      base,
      Offset(base.dx + 9, base.dy - 15),
      paint,
    );
  }

  @override
  bool shouldRepaint(
    covariant _UnknownWeatherPainter oldDelegate,
  ) {
    return false;
  }
}

// LANDSCAPE SEDERHANA BERDASARKAN KONDISI CUACA
class _WeatherLandscapePainter extends CustomPainter {
  final String condition;
  final List<Color> colors;

  const _WeatherLandscapePainter({
    required this.condition,
    required this.colors,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final name = condition.toLowerCase();

    final groundPaint = Paint()
      ..color = Colors.white.withOpacity(0.12)
      ..style = PaintingStyle.fill;

    // Bukit atau landscape bagian bawah
    final path = Path()
      ..moveTo(0, size.height * 0.78)
      ..quadraticBezierTo(
        size.width * 0.35,
        size.height * 0.60,
        size.width * 0.65,
        size.height * 0.78,
      )
      ..quadraticBezierTo(
        size.width * 0.85,
        size.height * 0.90,
        size.width,
        size.height * 0.72,
      )
      ..lineTo(size.width, size.height)
      ..lineTo(0, size.height)
      ..close();

    canvas.drawPath(path, groundPaint);

    // Dekorasi matahari
    if (name.contains('cerah') ||
        name.contains('clear') ||
        name.contains('sunny')) {
      final sunPaint = Paint()
        ..color = Colors.white.withOpacity(0.15);

      canvas.drawCircle(
        Offset(
          size.width * 0.82,
          size.height * 0.25,
        ),
        32,
        sunPaint,
      );
    }

    // Garis angin
    if (name.contains('angin') || name.contains('wind')) {
      final windPaint = Paint()
        ..color = Colors.white.withOpacity(0.35)
        ..strokeWidth = 2
        ..strokeCap = StrokeCap.round
        ..style = PaintingStyle.stroke;

      for (int i = 0; i < 3; i++) {
        final y = size.height * (0.28 + i * 0.09);

        canvas.drawLine(
          Offset(size.width * 0.60, y),
          Offset(size.width * 0.78, y - 5),
          windPaint,
        );
      }
    }

    // Garis hujan
    if (name.contains('hujan') ||
        name.contains('rain') ||
        name.contains('gerimis')) {
      final rainPaint = Paint()
        ..color = Colors.white.withOpacity(0.25)
        ..strokeWidth = 1.5;

      for (int i = 0; i < 9; i++) {
        final x = size.width * (0.55 + i * 0.045);

        canvas.drawLine(
          Offset(x, size.height * 0.25),
          Offset(x - 9, size.height * 0.48),
          rainPaint,
        );
      }
    }

    // Titik salju
    if (name.contains('salju') || name.contains('snow')) {
      final snowPaint = Paint()
        ..color = Colors.white.withOpacity(0.65);

      for (int i = 0; i < 8; i++) {
        final x = size.width * (0.55 + (i % 4) * 0.10);
        final y = size.height * (0.25 + (i ~/ 4) * 0.20);

        canvas.drawCircle(
          Offset(x, y),
          2,
          snowPaint,
        );
      }
    }

    // Kabut
    if (name.contains('kabut') ||
        name.contains('fog') ||
        name.contains('mist')) {
      final fogPaint = Paint()
        ..color = Colors.white.withOpacity(0.20)
        ..strokeWidth = 5
        ..strokeCap = StrokeCap.round;

      for (int i = 0; i < 3; i++) {
        final y = size.height * (0.60 + i * 0.10);

        canvas.drawLine(
          Offset(size.width * 0.52, y),
          Offset(size.width * 0.95, y),
          fogPaint,
        );
      }
    }
  }

  @override
  bool shouldRepaint(
    covariant _WeatherLandscapePainter oldDelegate,
  ) {
    return oldDelegate.condition != condition ||
        oldDelegate.colors != colors;
  }
}
