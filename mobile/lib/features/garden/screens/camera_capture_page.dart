
import 'dart:math' as math;

import 'package:camera/camera.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_svg/flutter_svg.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/constant/app_colors.dart';

class CameraCapturePage extends StatefulWidget {
  const CameraCapturePage({super.key});

  @override
  State<CameraCapturePage> createState() => _CameraCapturePageState();
}

class _CameraCapturePageState extends State<CameraCapturePage> {
  CameraController? _controller;

  bool _isCameraReady = false;
  bool _isTakingPicture = false;
  bool _isFlashOn = false;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();

    SystemChrome.setEnabledSystemUIMode(
      SystemUiMode.edgeToEdge,
    );

    _initializeCamera();
  }

  Future<void> _initializeCamera() async {
    try {
      final cameras = await availableCameras();

      if (cameras.isEmpty) {
        if (mounted) {
          setState(() {
            _errorMessage = 'Kamera tidak ditemukan.';
          });
        }
        return;
      }

      final backCamera = cameras.firstWhere(
        (camera) =>
            camera.lensDirection == CameraLensDirection.back,
        orElse: () => cameras.first,
      );

      final controller = CameraController(
        backCamera,
        ResolutionPreset.high,
        enableAudio: false,
      );

      await controller.initialize();

      if (!mounted) {
        await controller.dispose();
        return;
      }

      _controller = controller;

      await controller.setFlashMode(FlashMode.off);

      setState(() {
        _isCameraReady = true;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _errorMessage = 'Tidak dapat membuka kamera.';
      });
    }
  }

  Future<void> _takePicture() async {
    final controller = _controller;

    if (controller == null ||
        !controller.value.isInitialized ||
        _isTakingPicture) {
      return;
    }

    setState(() {
      _isTakingPicture = true;
    });

    try {
      final image = await controller.takePicture();

      if (!mounted) return;

      Navigator.pop(context, image);
    } catch (e) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Gagal mengambil foto.'),
        ),
      );
    } finally {
      if (mounted) {
        setState(() {
          _isTakingPicture = false;
        });
      }
    }
  }

  Future<void> _openGallery() async {
    final picker = ImagePicker();

    final image = await picker.pickImage(
      source: ImageSource.gallery,
      imageQuality: 85,
    );

    if (image != null && mounted) {
      Navigator.pop(context, image);
    }
  }

  Future<void> _toggleFlash() async {
    final controller = _controller;

    if (controller == null) return;

    try {
      final nextMode =
          _isFlashOn ? FlashMode.off : FlashMode.torch;

      await controller.setFlashMode(nextMode);

      if (!mounted) return;

      setState(() {
        _isFlashOn = !_isFlashOn;
      });
    } catch (_) {
      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Flash tidak tersedia.'),
        ),
      );
    }
  }

  Widget _buildCameraPreview() {
    final controller = _controller!;

    final screenSize = MediaQuery.of(context).size;
    final cameraAspectRatio = controller.value.aspectRatio;
    final screenAspectRatio =
        screenSize.width / screenSize.height;

    var scale = screenAspectRatio * cameraAspectRatio;

    if (scale < 1) {
      scale = 1 / scale;
    }

    return ClipRect(
      child: Transform.scale(
        scale: scale,
        child: Center(
          child: CameraPreview(controller),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _controller?.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnnotatedRegion<SystemUiOverlayStyle>(
      value: const SystemUiOverlayStyle(
        statusBarColor: Colors.transparent,
        statusBarIconBrightness: Brightness.light,
        systemNavigationBarColor: Colors.transparent,
        systemNavigationBarIconBrightness: Brightness.light,
        systemNavigationBarContrastEnforced: false,
      ),
      child: Scaffold(
        backgroundColor: Colors.black,
        body: Stack(
          fit: StackFit.expand,
          children: [
            // CAMERA PREVIEW FULL SCREEN
            if (_isCameraReady)
              _buildCameraPreview()
            else
              Center(
                child: _errorMessage != null
                    ? Text(
                        _errorMessage!,
                        style: const TextStyle(
                          color: Colors.white,
                          fontFamily: 'Alexandria',
                        ),
                      )
                    : const CircularProgressIndicator(
                        color: Colors.white,
                      ),
              ),

            // CAMERA FRAME
            if (_isCameraReady)
              const Positioned.fill(
                child: CustomPaint(
                  painter: CameraFramePainter(),
                ),
              ),

            // HEADER
            _buildHeader(),

            // BOTTOM CAMERA PANEL
            _buildBottomControls(),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader() {
    return Positioned(
      top: 0,
      left: 0,
      right: 0,
      child: Container(
        padding: EdgeInsets.only(
          top: MediaQuery.of(context).padding.top + 8,
          left: 22,
          right: 22,
          bottom: 14,
        ),
        decoration: BoxDecoration(
          color: AppColors.mediumGreen.withValues(
            alpha: 0.65,
          ),
          borderRadius: const BorderRadius.vertical(
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
                      child: SvgPicture.asset(
                        'assets/icons/back.svg',
                        width: 23,
                        height: 23,
                        colorFilter: const ColorFilter.mode(
                          Colors.white,
                          BlendMode.srcIn,
                        ),
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
              'Foto Tanaman',
              style: TextStyle(
                fontFamily: 'Alexandria',
                fontSize: 23,
                fontWeight: FontWeight.w700,
                color: AppColors.background,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildBottomControls() {
    return Positioned(
      left: 0,
      right: 0,
      bottom: 0,
      child: Container(
        padding: EdgeInsets.fromLTRB(
          35,
          22,
          35,
          MediaQuery.of(context).padding.bottom + 28,
        ),
        decoration: BoxDecoration(
          color: AppColors.mediumGreen.withValues(
            alpha: 0.65,
          ),
          borderRadius: const BorderRadius.vertical(
            top: Radius.circular(25),
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            // GALERI
            IconButton(
              onPressed: _openGallery,
              icon: const Icon(
                Icons.add_photo_alternate_outlined,
                color: Colors.white,
                size: 38,
              ),
            ),

            // SHUTTER
            GestureDetector(
              onTap: _takePicture,
              child: Container(
                width: 76,
                height: 76,
                padding: const EdgeInsets.all(5),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  border: Border.all(
                    color: Colors.white,
                    width: 4,
                  ),
                ),
                child: Container(
                  decoration: const BoxDecoration(
                    color: AppColors.background,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            ),

            // FLASH
            IconButton(
              onPressed: _toggleFlash,
              icon: Icon(
                _isFlashOn
                    ? Icons.flash_on
                    : Icons.flash_off,
                color: Colors.white,
                size: 38,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class CameraFramePainter extends CustomPainter {
  const CameraFramePainter();

  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = Colors.white.withValues(alpha: 0.55)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 3
      ..strokeCap = StrokeCap.round;

    const cornerLength = 52.0;
    const radius = 7.0;

    final left = 24.0;
    final right = size.width - 24.0;

    final top = size.height * 0.35;
    final bottom = size.height * 0.79;

    final path = Path()
      // KIRI ATAS
      ..moveTo(left, top + cornerLength)
      ..lineTo(left, top + radius)
      ..quadraticBezierTo(
        left,
        top,
        left + radius,
        top,
      )
      ..lineTo(left + cornerLength, top)

      // KANAN ATAS
      ..moveTo(right - cornerLength, top)
      ..lineTo(right - radius, top)
      ..quadraticBezierTo(
        right,
        top,
        right,
        top + radius,
      )
      ..lineTo(right, top + cornerLength)

      // KIRI BAWAH
      ..moveTo(left, bottom - cornerLength)
      ..lineTo(left, bottom - radius)
      ..quadraticBezierTo(
        left,
        bottom,
        left + radius,
        bottom,
      )
      ..lineTo(left + cornerLength, bottom)

      // KANAN BAWAH
      ..moveTo(right - cornerLength, bottom)
      ..lineTo(right - radius, bottom)
      ..quadraticBezierTo(
        right,
        bottom,
        right,
        bottom - radius,
      )
      ..lineTo(right, bottom - cornerLength);

    canvas.drawPath(path, paint);
  }

  @override
  bool shouldRepaint(
    covariant CameraFramePainter oldDelegate,
  ) {
    return false;
  }
}
