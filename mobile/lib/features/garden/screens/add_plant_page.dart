
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';
import '../services/plant_service.dart';

class AddPlantPage extends StatefulWidget {
  final String? farmId;

  const AddPlantPage({
    super.key,
    required this.farmId,
  });

  @override
  State<AddPlantPage> createState() => _AddPlantPageState();
}

class _AddPlantPageState extends State<AddPlantPage> {
  final TextEditingController _nameController =
      TextEditingController();

  final TextEditingController _typeController =
      TextEditingController();

  final PlantService _plantService = PlantService();

  // STATE TANGGAL
  DateTime? _seedlingDate;
  DateTime? _gardenPlantingDate;

  // STATE FORM
  String _placement = 'indoor';
  String _irrigationSchedule = 'every_3_5_days';

  bool _isSubmitting = false;

  // ASSET ICON
  static const String _backIcon = 'assets/icons/back.svg';
  static const String _uploadIcon = 'assets/icons/image_add.svg';
  static const String _nameIcon = 'assets/icons/Pencil.svg';
  static const String _plantIcon = 'assets/icons/Tree_Palm.svg';
  static const String _calendarIcon = 'assets/icons/Calendar.svg';

  // SVG ICON HELPER
  Widget _svgIcon(
    String path, {
    double size = 24,
    Color? color,
  }) {
    return SvgPicture.asset(
      path,
      width: size,
      height: size,
      colorFilter: color == null
          ? null
          : ColorFilter.mode(color, BlendMode.srcIn),
    );
  }

  // THEME DATE PICKER
  ThemeData _datePickerTheme(BuildContext context) {
    return Theme.of(context).copyWith(
      colorScheme: const ColorScheme.light(
        primary: AppColors.mediumGreen,
        onPrimary: Colors.white,
        surface: AppColors.background,
        onSurface: AppColors.darkGreen,
      ),
    );
  }

  // PILIH TANGGAL PENYEMAIAN BIBIT
  Future<void> _selectSeedlingDate() async {
    final selected = await showDatePicker(
      context: context,
      initialDate: _seedlingDate ?? DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime.now(),
      builder: (context, child) {
        return Theme(
          data: _datePickerTheme(context),
          child: child!,
        );
      },
    );

    if (selected != null) {
      setState(() {
        _seedlingDate = selected;
      });
    }
  }

  // PILIH TANGGAL PENANAMAN DI KEBUN
  Future<void> _selectGardenPlantingDate() async {
    final selected = await showDatePicker(
      context: context,
      initialDate: _gardenPlantingDate ??
          _seedlingDate ??
          DateTime.now(),
      firstDate: DateTime(2000),
      lastDate: DateTime.now(),
      builder: (context, child) {
        return Theme(
          data: _datePickerTheme(context),
          child: child!,
        );
      },
    );

    if (selected != null) {
      setState(() {
        _gardenPlantingDate = selected;
      });
    }
  }

  // FORMAT TANGGAL UNTUK TAMPILAN
  String _formatDate(DateTime? date) {
    if (date == null) return 'dd/mm/yyyy';

    return '${date.day.toString().padLeft(2, '0')}/'
        '${date.month.toString().padLeft(2, '0')}/'
        '${date.year}';
  }

  // SNACKBAR
  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  // SUBMIT FORM KE BACKEND
  Future<void> _submitForm() async {
    if (_isSubmitting) return;

    // VALIDASI FARM ID
    if (widget.farmId == null ||
        widget.farmId!.isEmpty) {
      _showMessage('Kebun belum dipilih.');
      return;
    }

    // VALIDASI INPUT
    if (_nameController.text.trim().isEmpty ||
        _typeController.text.trim().isEmpty ||
        _seedlingDate == null ||
        _gardenPlantingDate == null) {
      _showMessage(
        'Lengkapi data tanaman terlebih dahulu.',
      );
      return;
    }

    // VALIDASI TANGGAL
    if (_gardenPlantingDate!.isBefore(_seedlingDate!)) {
      _showMessage(
        'Tanggal penanaman tidak boleh sebelum tanggal pembibitan.',
      );
      return;
    }

    setState(() {
      _isSubmitting = true;
    });

    try {
      await _plantService.createPlant(
        farmId: widget.farmId!,
        label: _nameController.text.trim(),
        variety: _typeController.text.trim(),
        nurseryStartedAt: _seedlingDate!,
        plantedAt: _gardenPlantingDate!,
        placement: _placement,
        irrigationSchedule: _irrigationSchedule,
      );

      if (!mounted) return;

      _showMessage('Tanaman berhasil ditambahkan!');

      // Kembali ke Garden Page dan mengirim tanda refresh.
      Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;

      final errorMessage = e
          .toString()
          .replaceFirst('Exception: ', '');

      _showMessage(
        'Gagal menambahkan tanaman: $errorMessage',
      );
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }

  @override
  void dispose() {
    _nameController.dispose();
    _typeController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      body: LayoutBuilder(
        builder: (context, constraints) {
          return SingleChildScrollView(
            child: ConstrainedBox(
              constraints: BoxConstraints(
                minHeight: constraints.maxHeight,
              ),
              child: IntrinsicHeight(
                child: Column(
                  children: [
                    // HEADER
                    _buildHeader(),

                    // FORM
                    Expanded(
                      child: Padding(
                        padding: const EdgeInsets.fromLTRB(
                          21,
                          20,
                          21,
                          10,
                        ),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment:
                              CrossAxisAlignment.start,
                          children: [
                            // UPLOAD FOTO
                            const Text(
                              'Unggah Foto Tanaman',
                              style: _labelStyle,
                            ),

                            const SizedBox(height: 7),

                            _buildPhotoUpload(),

                            const SizedBox(height: 16),

                            // NAMA TANAMAN
                            const Text(
                              'Nama Tanaman',
                              style: _labelStyle,
                            ),

                            const SizedBox(height: 7),

                            _textField(
                              controller: _nameController,
                              hint: 'Pohon Mangga',
                              icon: _nameIcon,
                            ),

                            const SizedBox(height: 16),

                            // JENIS TANAMAN
                            const Text(
                              'Jenis Tanaman',
                              style: _labelStyle,
                            ),

                            const SizedBox(height: 7),

                            _textField(
                              controller: _typeController,
                              hint: 'Mangga Arumanis',
                              icon: _plantIcon,
                            ),

                            const SizedBox(height: 16),

                            // TANGGAL PEMBIBITAN
                            const Text(
                              'Tanggal Penyemaian Bibit',
                              style: _labelStyle,
                            ),

                            const SizedBox(height: 7),

                            _buildDateField(
                              date: _seedlingDate,
                              onTap: _selectSeedlingDate,
                            ),

                            const SizedBox(height: 16),

                            // TANGGAL PENANAMAN
                            const Text(
                              'Tanggal Penanaman di Kebun',
                              style: _labelStyle,
                            ),

                            const SizedBox(height: 7),

                            _buildDateField(
                              date: _gardenPlantingDate,
                              onTap: _selectGardenPlantingDate,
                            ),

                            const SizedBox(height: 16),

                            // LOKASI PENEMPATAN
                            const Text(
                              'Lokasi Penempatan',
                              style: _labelStyle,
                            ),

                            const SizedBox(height: 7),

                            _placementSelector(),

                            const SizedBox(height: 16),

                            // JADWAL PENYIRAMAN
                            const Text(
                              'Jadwal Penyiraman',
                              style: _labelStyle,
                            ),

                            const SizedBox(height: 7),

                            _buildWateringSchedule(),
                          ],
                        ),
                      ),
                    ),

                    // BUTTON SIMPAN
                    Padding(
                      padding: const EdgeInsets.fromLTRB(
                        21,
                        10,
                        21,
                        20,
                      ),
                      child: _buildSubmitButton(),
                    ),
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  // HEADER
  Widget _buildHeader() {
    return Container(
      width: double.infinity,
      padding: EdgeInsets.only(
        top: MediaQuery.of(context).padding.top + 8,
        left: 22,
        right: 22,
        bottom: 12,
      ),
      decoration: const BoxDecoration(
        color: AppColors.mediumGreen,
        borderRadius: BorderRadius.vertical(
          bottom: Radius.circular(28),
        ),
      ),
      child: Column(
        children: [
          SizedBox(
            height: 28,
            child: Stack(
              alignment: Alignment.center,
              children: [
                Align(
                  alignment: Alignment.centerLeft,
                  child: GestureDetector(
                    onTap: () => Navigator.pop(context),
                    child: _svgIcon(
                      _backIcon,
                      size: 23,
                      color: Colors.white,
                    ),
                  ),
                ),

                SvgPicture.asset(
                  'assets/images/logo_header.svg',
                  height: 25,
                  fit: BoxFit.contain,
                ),
              ],
            ),
          ),

          const SizedBox(height: 8),

          const Text(
            'Tambah Tanaman',
            style: TextStyle(
              fontSize: 23,
              fontWeight: FontWeight.w700,
              color: AppColors.background,
            ),
          ),
        ],
      ),
    );
  }

  // UPLOAD FOTO
  Widget _buildPhotoUpload() {
    return CustomPaint(
      foregroundPainter: DashedRoundedRectPainter(
        color: AppColors.mediumGreen,
        strokeWidth: 1.2,
        radius: 20,
        dashWidth: 8,
        dashSpace: 5,
      ),
      child: Container(
        width: double.infinity,
        height: 175,
        decoration: BoxDecoration(
          color: AppColors.fieldBackground,
          borderRadius: BorderRadius.circular(20),
        ),
        child: InkWell(
          borderRadius: BorderRadius.circular(20),
          onTap: () {
            _showMessage(
              'Fitur pilih foto akan dihubungkan berikutnya.',
            );
          },
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _svgIcon(
                _uploadIcon,
                size: 65,
                color: AppColors.mediumGreen,
              ),

              const SizedBox(height: 10),

              const Text(
                'Ketuk untuk memilih atau ambil foto',
                style: TextStyle(
                  color: AppColors.mediumGreen,
                  fontSize: 14,
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  // TEXT FIELD
  Widget _textField({
    required TextEditingController controller,
    required String hint,
    required String icon,
  }) {
    return SizedBox(
      height: 50,
      child: TextField(
        controller: controller,
        style: const TextStyle(
          fontSize: 14,
          color: AppColors.darkGreen,
        ),
        decoration: InputDecoration(
          hintText: hint,
          hintStyle: const TextStyle(
            color: AppColors.mediumGreen,
            fontSize: 14,
            fontWeight: FontWeight.w500,
          ),
          prefixIcon: Padding(
            padding: const EdgeInsets.all(14),
            child: _svgIcon(
              icon,
              size: 22,
              color: AppColors.mediumGreen,
            ),
          ),
          filled: true,
          fillColor: AppColors.fieldBackground,
          contentPadding: const EdgeInsets.symmetric(
            vertical: 12,
          ),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: BorderSide.none,
          ),
          enabledBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: BorderSide.none,
          ),
          focusedBorder: OutlineInputBorder(
            borderRadius: BorderRadius.circular(18),
            borderSide: const BorderSide(
              color: AppColors.mediumGreen,
              width: 1,
            ),
          ),
        ),
      ),
    );
  }

  // DATE FIELD
  Widget _buildDateField({
    required DateTime? date,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: Container(
        height: 50,
        padding: const EdgeInsets.symmetric(
          horizontal: 16,
        ),
        decoration: BoxDecoration(
          color: AppColors.fieldBackground,
          borderRadius: BorderRadius.circular(18),
        ),
        child: Row(
          children: [
            _svgIcon(
              _calendarIcon,
              size: 22,
              color: AppColors.mediumGreen,
            ),

            const SizedBox(width: 12),

            Text(
              _formatDate(date),
              style: TextStyle(
                color: date == null
                    ? AppColors.mediumGreen
                    : AppColors.darkGreen,
                fontSize: 14,
                fontWeight: FontWeight.w500,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // SELECTOR INDOOR / OUTDOOR
  Widget _placementSelector() {
    return Container(
      height: 50,
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: BorderRadius.circular(30),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(30),
        child: Row(
          children: [
            Expanded(
              child: _placementItem(
                value: 'indoor',
                label: 'Dalam Ruangan',
              ),
            ),

            Expanded(
              child: _placementItem(
                value: 'outdoor',
                label: 'Luar Ruangan',
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _placementItem({
    required String value,
    required String label,
  }) {
    final isSelected = _placement == value;

    return GestureDetector(
      onTap: () {
        setState(() {
          _placement = value;
        });
      },
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 180),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: isSelected
              ? AppColors.mediumGreen
              : AppColors.fieldBackground,
        ),
        child: Text(
          label,
          textAlign: TextAlign.center,
          style: TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            color: isSelected
                ? Colors.white
                : AppColors.mediumGreen,
          ),
        ),
      ),
    );
  }

  // JADWAL PENYIRAMAN
  Widget _buildWateringSchedule() {
    const schedules = [
      {
        'value': 'daily',
        'label': 'Setiap hari',
      },
      {
        'value': 'every_3_5_days',
        'label': 'Setiap 3–5 hari',
      },
      {
        'value': 'weekly',
        'label': 'Seminggu sekali',
      },
      {
        'value': 'never',
        'label': 'Tidak dijadwalkan',
      },
    ];

    return Container(
      height: 55,
      padding: const EdgeInsets.symmetric(
        horizontal: 16,
      ),
      decoration: BoxDecoration(
        color: AppColors.fieldBackground,
        borderRadius: BorderRadius.circular(18),
      ),
      child: DropdownButtonHideUnderline(
        child: DropdownButton<String>(
          value: _irrigationSchedule,
          isExpanded: true,
          icon: const Icon(
            Icons.keyboard_arrow_down_rounded,
            color: AppColors.mediumGreen,
          ),
          style: const TextStyle(
            fontSize: 14,
            color: AppColors.darkGreen,
            fontWeight: FontWeight.w500,
          ),
          items: schedules.map((schedule) {
            return DropdownMenuItem<String>(
              value: schedule['value'],
              child: Text(schedule['label']!),
            );
          }).toList(),
          onChanged: (value) {
            if (value == null) return;

            setState(() {
              _irrigationSchedule = value;
            });
          },
        ),
      ),
    );
  }

  // BUTTON SIMPAN
  Widget _buildSubmitButton() {
    return SizedBox(
      width: double.infinity,
      height: 70,
      child: ElevatedButton(
        onPressed: _isSubmitting ? null : _submitForm,
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF6B8F70),
          foregroundColor: Colors.white,
          disabledBackgroundColor: AppColors.mediumGreen,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
          ),
        ),
        child: _isSubmitting
            ? const SizedBox(
                width: 24,
                height: 24,
                child: CircularProgressIndicator(
                  strokeWidth: 2.5,
                  color: Colors.white,
                ),
              )
            : const Text(
                'Simpan',
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.w600,
                ),
              ),
      ),
    );
  }

  // LABEL STYLE
  static const TextStyle _labelStyle = TextStyle(
    fontSize: 14,
    fontWeight: FontWeight.w700,
    color: AppColors.textSecondary,
  );
}

// DASHED BORDER PAINTER
class DashedRoundedRectPainter extends CustomPainter {
  final Color color;
  final double strokeWidth;
  final double radius;
  final double dashWidth;
  final double dashSpace;

  DashedRoundedRectPainter({
    required this.color,
    this.strokeWidth = 1.5,
    this.radius = 20,
    this.dashWidth = 8,
    this.dashSpace = 5,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.stroke
      ..strokeWidth = strokeWidth;

    final rect = Rect.fromLTWH(
      strokeWidth / 2,
      strokeWidth / 2,
      size.width - strokeWidth,
      size.height - strokeWidth,
    );

    final path = Path()
      ..addRRect(
        RRect.fromRectAndRadius(
          rect,
          Radius.circular(radius),
        ),
      );

    for (final metric in path.computeMetrics()) {
      double distance = 0;

      while (distance < metric.length) {
        final end = (distance + dashWidth)
            .clamp(0.0, metric.length)
            .toDouble();

        canvas.drawPath(
          metric.extractPath(distance, end),
          paint,
        );

        distance += dashWidth + dashSpace;
      }
    }
  }

  @override
  bool shouldRepaint(
    covariant DashedRoundedRectPainter oldDelegate,
  ) {
    return oldDelegate.color != color ||
        oldDelegate.strokeWidth != strokeWidth ||
        oldDelegate.radius != radius ||
        oldDelegate.dashWidth != dashWidth ||
        oldDelegate.dashSpace != dashSpace;
  }
}
