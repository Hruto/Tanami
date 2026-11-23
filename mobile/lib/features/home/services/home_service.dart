
import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';
import '../models/home_model.dart';

class HomeService {
  final ApiClient _apiClient = ApiClient();

  Future<HomeModel> getHomeData() async {
    final response = await _apiClient.get(
      '${ApiConfig.baseUrl}/home',
    );

    final data = response['data'];

    if (data is! Map<String, dynamic>) {
      throw Exception('Format data Home dari server tidak valid.');
    }

    return HomeModel.fromJson(data);
  }
}
