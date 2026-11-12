
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class TokenStorage {
  static const _storage = FlutterSecureStorage();

  // Menyimpan access token dan refresh token
  static Future<void> saveTokens({
    required String accessToken,
    required String refreshToken,
  }) async {
    await _storage.write(
      key: 'access_token',
      value: accessToken,
    );

    await _storage.write(
      key: 'refresh_token',
      value: refreshToken,
    );
  }

  // Mengambil access token
  static Future<String?> getAccessToken() async {
    return await _storage.read(key: 'access_token');
  }

  // Mengambil refresh token
  static Future<String?> getRefreshToken() async {
    return await _storage.read(key: 'refresh_token');
  }

  // Menghapus token ketika logout
  static Future<void> clearTokens() async {
    await _storage.delete(key: 'access_token');
    await _storage.delete(key: 'refresh_token');
  }
}

