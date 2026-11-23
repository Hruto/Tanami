import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';
import '../models/weather_model.dart';

class WeatherService {
  final ApiClient _apiClient = ApiClient();

  Future<WeatherModel> getWeather(String farmId) async {
    final response = await _apiClient.get(
      '${ApiConfig.baseUrl}/farms/$farmId/weather',
    );

    final data = response['data'];

    if (data is! Map<String, dynamic>) {
      throw Exception('Format data cuaca dari server tidak valid.');
    }

    return WeatherModel.fromJson(data);
  }
}