
import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';
import '../models/user_model.dart';

class UserService {
  final ApiClient _apiClient = ApiClient();

  Future<UserModel> getCurrentUser() async {
    final response = await _apiClient.get(
      '${ApiConfig.baseUrl}/users/me',
    );

    final data = response['data'];

    if (data is! Map<String, dynamic>) {
      throw Exception('Format data profil pengguna tidak valid.');
    }

    return UserModel.fromJson(data);
  }
}
