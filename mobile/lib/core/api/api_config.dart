import 'package:flutter/foundation.dart';

/// Where the Tanami API lives.
///
/// `127.0.0.1` is the development machine only when the app runs on desktop or
/// in a browser. An Android emulator reaches the machine's loopback through
/// `10.0.2.2`, and a physical phone needs the machine's LAN address, so both
/// are covered by [baseUrl] plus the build-time override:
///
/// ```bash
/// flutter run --dart-define=API_BASE_URL=http://192.168.1.10:8000/api/v1
/// ```
class ApiConfig {
  ApiConfig._();

  static const String _override = String.fromEnvironment('API_BASE_URL');

  static String get baseUrl {
    if (_override.isNotEmpty) {
      return _override;
    }
    if (!kIsWeb && defaultTargetPlatform == TargetPlatform.android) {
      // The Android emulator's alias for the host loopback interface.
      return 'http://10.0.2.2:8000/api/v1';
    }
    return 'http://127.0.0.1:8000/api/v1';
  }

  static String get register => '$baseUrl/auth/register';

  static String get login => '$baseUrl/auth/login';

  static String get refresh => '$baseUrl/auth/refresh';

  static String get logout => '$baseUrl/auth/logout';
}
