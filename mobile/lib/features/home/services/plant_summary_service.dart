
import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';
import '../models/plant_summary_model.dart';

class PlantSummaryService {
  final ApiClient _apiClient = ApiClient();

  Future<PlantSummaryModel> getPlantSummary(String farmId) async {
    final response = await _apiClient.get(
      '${ApiConfig.baseUrl}/farms/$farmId/plants?include_archived=false',
    );

    final data = response['data'];

    if (data is! List) {
      throw Exception('Format data tanaman dari server tidak valid.');
    }

    int healthy = 0;
    int sick = 0;
    int total = 0;

    for (final item in data) {
      if (item is! Map<String, dynamic>) continue;

      total++;

      final healthStatus = item['health_status'];

      if (healthStatus == 'healthy') {
        healthy++;
      } else if (healthStatus == 'sick') {
        sick++;
      }
    }

    return PlantSummaryModel(
      total: total,
      healthy: healthy,
      sick: sick,
    );
  }
}
