
import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';
import '../../../core/storage/token_storage.dart';

import '../models/auth_response.dart';
import '../models/login_request.dart';
import '../models/register_request.dart';

class AuthService {
  final ApiClient _apiClient = ApiClient();

  // Register
  Future<AuthResponse> register(
    RegisterRequest request,
  ) async {
    final response = await _apiClient.post(
      ApiConfig.register,
      request.toJson(),
    );

    final authResponse = AuthResponse.fromJson(
      response['data'],
    );

    await TokenStorage.saveTokens(
      accessToken: authResponse.accessToken,
      refreshToken: authResponse.refreshToken,
    );

    return authResponse;
  }

  // Login
  Future<AuthResponse> login(
    LoginRequest request,
  ) async {
    final response = await _apiClient.post(
      ApiConfig.login,
      request.toJson(),
    );

    final authResponse = AuthResponse.fromJson(
      response['data'],
    );

    await TokenStorage.saveTokens(
      accessToken: authResponse.accessToken,
      refreshToken: authResponse.refreshToken,
    );

    return authResponse;
  }
}
