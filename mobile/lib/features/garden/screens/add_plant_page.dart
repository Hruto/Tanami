import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:image_picker/image_picker.dart';
import 'camera_capture_page.dart';
import '../../../core/constant/app_colors.dart';
import '../services/plant_service.dart';
import '../widgets/custom_text_field.dart';
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
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _typeController = TextEditingController();
  final PlantService _plantService = PlantService();
  final ImagePicker _imagePicker = ImagePicker();
  XFile? _selectedImage;
  Uint8List? _selectedImageBytes;
  // Menyimpan ID tanaman jika data berhasil dibuat,
  // tetapi upload foto belum berhasil.
  String? _createdPlantId;
  DateTime? _seedlingDate;
  DateTime? _gardenPlantingDate;
  String _placement = 'indoor';
  String _irrigationSchedule = 'every_3_5_days';
  bool _isSubmitting = false;
  bool _showValidationErrors = false;
  // Menyimpan pesan validasi jenis tanaman yang dikirim backend.
  String? _typeServerError;
  // Asset icons
  static const String _backIcon = 'assets/icons/back.svg';
  static const String _uploadIcon = 'assets/icons/image_add.svg';
  static const String _nameIcon = 'assets/icons/Pencil.svg';
  static const String _calendarIcon = 'assets/icons/calendar.svg';
  static const String _pencilIcon = 'assets/icons/pencil.svg';
  static const String _treePalmIcon = 'assets/icons/tree_Palm.svg';
  static const TextStyle _labelStyle = TextStyle(
    fontFamily: 'Alexandria',
    fontSize: 13,
    fontWeight: FontWeight.w700,
    color: AppColors.textSecondary,
  );
  // SVG helper
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
  // Theme date picker
ThemeData _datePickerTheme(BuildContext context) {
  return Theme.of(context).copyWith(
    colorScheme: const ColorScheme.light(
      primary: AppColors.mediumGreen,
      onPrimary: Colors.white,
      surface: AppColors.background,
      onSurface: AppColors.mediumGreen,
    ),
    textTheme: const TextTheme(
      headlineLarge: TextStyle(fontFamily: 'Alexandria'),
      headlineMedium: TextStyle(fontFamily: 'Alexandria'),
      titleLarge: TextStyle(
        fontFamily: 'Alexandria',
        fontWeight: FontWeight.w600,
        color: AppColors.mediumGreen,
      ),
      bodyLarge: TextStyle(
        fontFamily: 'Alexandria',
        color: AppColors.mediumGreen,
      ),
      bodyMedium: TextStyle(
        fontFamily: 'Alexandria',
        color: AppColors.mediumGreen,
      ),
    ),
    datePickerTheme: DatePickerThemeData(
      backgroundColor: AppColors.background,
      headerBackgroundColor: AppColors.mediumGreen,
      headerForegroundColor: Colors.white,
      headerHeadlineStyle: const TextStyle(
        fontFamily: 'Alexandria',
        fontSize: 24,
        fontWeight: FontWeight.w700,
        color: Colors.white,
      ),
      headerHelpStyle: const TextStyle(
        fontFamily: 'Alexandria',
        fontSize: 13,
        fontWeight: FontWeight.w500,
        color: Colors.white,
      ),
      weekdayStyle: const TextStyle(
        fontFamily: 'Alexandria',
        fontSize: 11,
        fontWeight: FontWeight.w600,
        color: AppColors.mediumGreen,
      ),
      dayStyle: const TextStyle(
        fontFamily: 'Alexandria',
        fontSize: 13,
        fontWeight: FontWeight.w500,
      ),
      yearStyle: const TextStyle(
        fontFamily: 'Alexandria',
        fontSize: 14,
        fontWeight: FontWeight.w600,
      ),
      // Tanggal terpilih menggunakan lingkaran hijau penuh.
      // State selected diprioritaskan, termasuk saat tanggal terpilih adalah hari ini.
      todayForegroundColor: WidgetStateProperty.resolveWith<Color?>((states) {
        if (states.contains(WidgetState.selected)) return Colors.white;
        return AppColors.mediumGreen;
      }),
      todayBackgroundColor: WidgetStateProperty.resolveWith<Color?>((states) {
        if (states.contains(WidgetState.selected)) {
          return AppColors.mediumGreen;
        }
        return AppColors.successBackground;
      }),
      dayForegroundColor: WidgetStateProperty.resolveWith<Color?>((states) {
        if (states.contains(WidgetState.selected)) return Colors.white;
        return AppColors.mediumGreen;
      }),
      dayBackgroundColor: WidgetStateProperty.resolveWith<Color?>((states) {
        if (states.contains(WidgetState.selected)) {
          return AppColors.mediumGreen;
        }
        return Colors.transparent;
      }),
      todayBorder: const BorderSide(color: AppColors.mediumGreen, width: 1),
      confirmButtonStyle: TextButton.styleFrom(
        foregroundColor: AppColors.mediumGreen,
        textStyle: const TextStyle(
          fontFamily: 'Alexandria',
          fontWeight: FontWeight.w600,
        ),
      ),
      cancelButtonStyle: TextButton.styleFrom(
        foregroundColor: AppColors.grey,
        textStyle: const TextStyle(
          fontFamily: 'Alexandria',
          fontWeight: FontWeight.w500,
        ),
      ),
    ),
  );
}
  // Pilih tanggal penyemaian bibit
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
        // Jika tanggal penyemaian berubah dan tanggal
        // penanaman menjadi lebih awal, reset tanggal penanaman.
        if (_gardenPlantingDate != null &&
            _gardenPlantingDate!.isBefore(selected)) {
          _gardenPlantingDate = null;
        }
      });
    }
  }
  // Pilih tanggal penanaman di kebun
  Future<void> _selectGardenPlantingDate() async {
    final selected = await showDatePicker(
      context: context,
      initialDate: _gardenPlantingDate ?? _seedlingDate ?? DateTime.now(),
      firstDate: _seedlingDate ?? DateTime(2000),
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
  // Format tanggal untuk tampilan
  String _formatDate(DateTime? date) {
    if (date == null) return 'dd/mm/yyyy';
    return '${date.day.toString().padLeft(2, '0')}/'
        '${date.month.toString().padLeft(2, '0')}/'
        '${date.year}';
  }
  // Notifikasi sukses dengan gaya banner seperti notifikasi login/register.
  void _showSuccessToast() {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(
        SnackBar(
          duration: const Duration(seconds: 3),
          behavior: SnackBarBehavior.floating,
          backgroundColor: Colors.transparent,
          elevation: 0,
          padding: EdgeInsets.zero,
          margin: const EdgeInsets.fromLTRB(16, 0, 16, 16),
          content: Container(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
            decoration: BoxDecoration(
              color: AppColors.successBackground,
              borderRadius: BorderRadius.circular(16),
              boxShadow: [
                BoxShadow(
                  color: AppColors.darkGreen.withValues(alpha: 0.08),
                  blurRadius: 14,
                  offset: const Offset(0, 4),
                ),
              ],
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    border: Border.all(
                      color: AppColors.mediumGreen,
                      width: 1.6,
                    ),
                  ),
                  child: const Icon(
                    Icons.check_rounded,
                    color: AppColors.mediumGreen,
                    size: 19,
                  ),
                ),
                const SizedBox(width: 12),
                const Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Text(
                        'Tanaman Berhasil Ditambahkan!',
                        style: TextStyle(
                          fontFamily: 'Alexandria',
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: AppColors.mediumGreen,
                        ),
                      ),
                      SizedBox(height: 4),
                      Text(
                        'Data tanaman berhasil disimpan. Selamat menggunakan Tanami.',
                        style: TextStyle(
                          fontFamily: 'Alexandria',
                          fontSize: 9,
                          height: 1.4,
                          fontWeight: FontWeight.w400,
                          color: AppColors.darkGreen,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
        ),
      );
  }
  // Snackbar
  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          message,
          style: const TextStyle(fontFamily: 'Alexandria'),
        ),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }
  // Bottom sheet sumber foto
  Future<void> _openCameraPage() async {
  final image = await Navigator.push<XFile>(
    context,
    MaterialPageRoute(builder: (_) => const CameraCapturePage()),
  );
  if (image == null) return;
  final bytes = await image.readAsBytes();
  if (!mounted) return;
  setState(() {
    _selectedImage = image;
    _selectedImageBytes = bytes;
  });
}

Future<void> _showPhotoSourcePicker() async {
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: AppColors.background,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(
          top: Radius.circular(24),
        ),
      ),
      builder: (context) {
        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(20, 20, 20, 24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Container(
                  width: 42,
                  height: 4,
                  decoration: BoxDecoration(
                    color: AppColors.lightGreen,
                    borderRadius: BorderRadius.circular(10),
                  ),
                ),
                const SizedBox(height: 20),
                const Text(
                  'Pilih Foto Tanaman',
                  style: TextStyle(
                    fontFamily: 'Alexandria',
                    fontSize: 17,
                    fontWeight: FontWeight.w700,
                    color: AppColors.darkGreen,
                  ),
                ),
                const SizedBox(height: 18),
                _photoSourceOption(
                  icon: Icons.camera_alt_outlined,
                  label: 'Ambil Foto',
                  onTap: () {
                    Navigator.pop(context);
                    _pickImage(ImageSource.camera);
                  },
                ),
                const SizedBox(height: 10),
                _photoSourceOption(
                  icon: Icons.photo_library_outlined,
                  label: 'Pilih dari Galeri',
                  onTap: () {
                    Navigator.pop(context);
                    _pickImage(ImageSource.gallery);
                  },
                ),
              ],
            ),
          ),
        );
      },
    );
  }
  Widget _photoSourceOption({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(16),
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 15,
        ),
        decoration: BoxDecoration(
          color: AppColors.fieldBackground,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Icon(
              icon,
              color: AppColors.mediumGreen,
              size: 23,
            ),
            const SizedBox(width: 14),
            Text(
              label,
              style: const TextStyle(
                fontFamily: 'Alexandria',
                fontSize: 13,
                fontWeight: FontWeight.w600,
                color: AppColors.darkGreen,
              ),
            ),
          ],
        ),
      ),
    );
  }
  // Pilih foto dari kamera atau galeri
  Future<void> _pickImage(ImageSource source) async {
    try {
      final image = await _imagePicker.pickImage(
        source: source,
        imageQuality: 85,
      );
      if (image == null) return;
      final bytes = await image.readAsBytes();
      if (!mounted) return;
      setState(() {
        _selectedImage = image;
        _selectedImageBytes = bytes;
      });
    } catch (e) {
      if (!mounted) return;
      _showMessage('Gagal memilih foto: $e');
    }
  }
  String? get _nameError {
    if (!_showValidationErrors) return null;
    return _nameController.text.trim().isEmpty
        ? 'Nama tanaman wajib diisi.'
        : null;
  }
  String? get _typeError {
    if (!_showValidationErrors) return null;
    return _typeController.text.trim().isEmpty
        ? 'Jenis tanaman wajib diisi.'
        : null;
  }
  // Pesan error lokal atau dari backend ditampilkan di bawah field jenis tanaman.
  String? get _typeFieldError => _typeError ?? _typeServerError;
  String? get _seedlingDateError {
    if (!_showValidationErrors) return null;
    return _seedlingDate == null
        ? 'Tanggal penyemaian wajib diisi.'
        : null;
  }
  String? get _gardenPlantingDateError {
    if (!_showValidationErrors) return null;
    if (_gardenPlantingDate == null) {
      return 'Tanggal penanaman wajib diisi.';
    }
    if (_seedlingDate != null &&
        _gardenPlantingDate!.isBefore(_seedlingDate!)) {
      return 'Tanggal penanaman tidak boleh sebelum tanggal penyemaian.';
    }
    return null;
  }
  String? get _photoError {
    if (!_showValidationErrors) return null;
    return _selectedImageBytes == null
        ? 'Foto tanaman wajib diunggah.'
        : null;
  }
  // Submit form ke backend
  Future<void> _submitForm() async {
    if (_isSubmitting) return;
    setState(() {
      _showValidationErrors = true;
    });
    if (widget.farmId == null || widget.farmId!.isEmpty) {
      _showMessage('Kebun belum dipilih.');
      return;
    }
    final hasError = _nameError != null ||
        _typeFieldError != null ||
        _seedlingDateError != null ||
        _gardenPlantingDateError != null ||
        _photoError != null;
    if (hasError) return;
    setState(() {
      _isSubmitting = true;
    });
    try {
      // Buat data tanaman jika belum pernah berhasil dibuat.
      if (_createdPlantId == null) {
        final plant = await _plantService.createPlant(
          farmId: widget.farmId!,
          label: _nameController.text.trim(),
          variety: _typeController.text.trim(),
          nurseryStartedAt: _seedlingDate!,
          plantedAt: _gardenPlantingDate!,
          placement: _placement,
          irrigationSchedule: _irrigationSchedule,
        );
        _createdPlantId = plant.id;
      }
      // Upload foto dokumentasi tanaman.
      await _plantService.uploadPlantPhoto(
        plantId: _createdPlantId!,
        imageBytes: _selectedImageBytes!,
        fileName: _selectedImage!.name,
      );
      if (!mounted) return;
      _showSuccessToast();
      Navigator.pop(context, true);
    } catch (e) {
      if (!mounted) return;
      final errorMessage = e.toString().replaceFirst('Exception: ', '').trim();
      final normalizedError = errorMessage.toLowerCase();
      final isPlantTypeValidationError =
          normalizedError.contains('jenis tanaman') &&
          (normalizedError.contains('mangga') ||
              normalizedError.contains('jeruk') ||
              normalizedError.contains('tomat'));
      if (_createdPlantId != null) {
        _showMessage(
          'Data tanaman sudah dibuat, tetapi foto gagal diunggah. '
          'Tekan Simpan untuk mencoba upload kembali. '
          'Detail: $errorMessage',
        );
      } else if (isPlantTypeValidationError) {
        // Tampilkan pesan asli dari backend tepat di bawah field jenis tanaman.
        setState(() {
          _typeServerError = errorMessage;
        });
      } else {
        _showMessage('Gagal menambahkan tanaman: $errorMessage');
      }
    } finally {
      if (mounted) {
        setState(() {
          _isSubmitting = false;
        });
      }
    }
  }
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
                    _buildHeader(),
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
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Upload foto
                            const Text(
                              'Unggah Foto Tanaman',
                              style: _labelStyle,
                            ),
                            const SizedBox(height: 7),
                            _buildPhotoUpload(),
                            if (_photoError != null) ...[
                              const SizedBox(height: 6),
                              Row(
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
                                      _photoError!,
                                      style: const TextStyle(
                                        fontFamily: 'Alexandria',
                                        fontSize: 11,
                                        fontWeight: FontWeight.w500,
                                        color: AppColors.red,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ],
                            const SizedBox(height: 16),
                            // Nama tanaman
                            GardenTextField(
                              controller: _nameController,
                              label: 'Nama Tanaman',
                              hint: 'Masukan Nama Tanaman',
                              iconAsset: _pencilIcon,
                              errorText: _nameError,
                              onChanged: (_) => setState(() {}),
                            ),
                            const SizedBox(height: 16),
                            // Jenis tanaman
                            GardenTextField(
                              controller: _typeController,
                              label: 'Jenis Tanaman',
                              hint: 'Mangga/Tomat/Jeruk',
                              iconAsset: _treePalmIcon,
                              errorText: _typeFieldError,
                              onChanged: (_) {
                                setState(() {
                                  _typeServerError = null;
                                });
                              },
                            ),
                            const SizedBox(height: 16),
                            // Tanggal penyemaian
                            GardenDateField(
                              label: 'Tanggal Penyemaian Bibit',
                              iconAsset: _calendarIcon,
                              value: _formatDate(_seedlingDate),
                              isPlaceholder: _seedlingDate == null,
                              onTap: _selectSeedlingDate,
                              errorText: _seedlingDateError,
                            ),
                            const SizedBox(height: 16),
                            // Tanggal penanaman
                            GardenDateField(
                              label: 'Tanggal Penanaman di Kebun',
                              iconAsset: _calendarIcon,
                              value: _formatDate(_gardenPlantingDate),
                              isPlaceholder: _gardenPlantingDate == null,
                              onTap: _selectGardenPlantingDate,
                              errorText: _gardenPlantingDateError,
                            ),
                            const SizedBox(height: 16),
                            // Lokasi penempatan
                            const Text(
                              'Lokasi Penempatan',
                              style: _labelStyle,
                            ),
                            const SizedBox(height: 7),
                            _placementSelector(),
                            const SizedBox(height: 16),
                            // Jadwal penyiraman
                            GardenDropdownField(
                              label: 'Jadwal Penyiraman',
                              value: _irrigationSchedule,
                              items: const [
                                DropdownMenuItem(
                                  value: 'daily',
                                  child: Text('Setiap hari'),
                                ),
                                DropdownMenuItem(
                                  value: 'every_3_5_days',
                                  child: Text('Setiap 3–5 hari'),
                                ),
                                DropdownMenuItem(
                                  value: 'weekly',
                                  child: Text('Seminggu sekali'),
                                ),
                                DropdownMenuItem(
                                  value: 'never',
                                  child: Text('Tidak dijadwalkan'),
                                ),
                              ],
                              onChanged: (value) {
                                if (value == null) return;
                                setState(() {
                                  _irrigationSchedule = value;
                                });
                              },
                            ),
                          ],
                        ),
                      ),
                    ),
                    // Tombol simpan
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
  // Header
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
                    child: Transform.translate(
                      offset: const Offset(0,  5),
                      child: _svgIcon(_backIcon, size: 23, color: Colors.white),
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
              fontFamily: 'Alexandria',
              fontSize: 23,
              fontWeight: FontWeight.w700,
              color: AppColors.background,
            ),
          ),
        ],
      ),
    );
  }
  // Upload foto
  Widget _buildPhotoUpload() {
    final hasImage = _selectedImageBytes != null;
    return CustomPaint(
      foregroundPainter: hasImage
          ? null
          : DashedRoundedRectPainter(
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
          border: hasImage
              ? Border.all(
                  color: AppColors.mediumGreen,
                  width: 1.2,
                )
              : null,
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(20),
          child: hasImage
              ? Stack(
                  fit: StackFit.expand,
                  children: [
                    Image.memory(
                      _selectedImageBytes!,
                      fit: BoxFit.cover,
                    ),
                    Positioned(
                      right: 10,
                      top: 10,
                      child: Row(
                        children: [
                          _photoActionButton(
                            icon: Icons.edit_outlined,
                            onTap: _openCameraPage,
                          ),
                          const SizedBox(width: 8),
                          _photoActionButton(
                            icon: Icons.delete_outline,
                            onTap: () {
                              setState(() {
                                _selectedImage = null;
                                _selectedImageBytes = null;
                              });
                            },
                          ),
                        ],
                      ),
                    ),
                  ],
                )
              : InkWell(
                  onTap: _openCameraPage,
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
                          fontFamily: 'Alexandria',
                          color: AppColors.mediumGreen,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                      const SizedBox(height: 5),
                    ],
                  ),
                ),
        ),
      ),
    );
  }
  Widget _photoActionButton({
    required IconData icon,
    required VoidCallback onTap,
  }) {
    return Material(
      color: AppColors.darkGreen.withValues(alpha: 0.75),
      shape: const CircleBorder(),
      child: InkWell(
        onTap: onTap,
        customBorder: const CircleBorder(),
        child: Padding(
          padding: const EdgeInsets.all(9),
          child: Icon(
            icon,
            color: Colors.white,
            size: 20,
          ),
        ),
      ),
    );
  }
  // Selector indoor / outdoor
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
            fontFamily: 'Alexandria',
            fontSize: 12,
            fontWeight: FontWeight.w600,
            color: isSelected
                ? Colors.white
                : AppColors.mediumGreen,
          ),
        ),
      ),
    );
  }
  // Tombol simpan
  Widget _buildSubmitButton() {
    return SizedBox(
      width: double.infinity,
      height: 70,
      child: ElevatedButton(
        onPressed: _isSubmitting ? null : _submitForm,
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.mediumGreen,
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
                  fontFamily: 'Alexandria',
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                ),
              ),
      ),
    );
  }
}
// Dashed border painter
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
