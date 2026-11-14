import 'package:flutter/foundation.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:mobile/core/api/api_config.dart';

/// The same compile-time define `ApiConfig` reads, so a verification run with
/// `--dart-define=API_BASE_URL=...` does not look like a regression here.
const String _override = String.fromEnvironment('API_BASE_URL');

String _expected(String fallback) => _override.isNotEmpty ? _override : fallback;

void main() {
  tearDown(() => debugDefaultTargetPlatformOverride = null);

  test('desktop and web use the loopback address', () {
    // `flutter test` defaults to the Android platform, so be explicit here.
    debugDefaultTargetPlatformOverride = TargetPlatform.windows;

    final base = _expected('http://127.0.0.1:8000/api/v1');
    expect(ApiConfig.baseUrl, base);
    expect(ApiConfig.login, '$base/auth/login');
  });

  test('an Android build targets the host through 10.0.2.2', () {
    debugDefaultTargetPlatformOverride = TargetPlatform.android;

    final base = _expected('http://10.0.2.2:8000/api/v1');
    expect(ApiConfig.baseUrl, base);
    expect(ApiConfig.register, '$base/auth/register');
  });
}
