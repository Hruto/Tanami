
import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';
import '../models/plant_model.dart';

class PlantService {
  final ApiClient _apiClient = ApiClient();

  // GET: Mengambil semua tanaman dalam kebun
  Future<List<PlantModel>> getPlants(String farmId) async {
    final response = await _apiClient.get(
      '${ApiConfig.baseUrl}/farms/$farmId/plants?include_archived=false',
    );

    final data = response['data'];

    if (data is! List) {
      throw Exception(
        'Format data tanaman dari server tidak valid.',
      );
    }

    return data.map((item) {
      return PlantModel.fromJson(
        Map<String, dynamic>.from(item),
      );
    }).toList();
  }

  // POST: Membuat tanaman baru
  Future<PlantModel> createPlant({
    required String farmId,
    required String label,
    required String variety,
    required DateTime nurseryStartedAt,
    DateTime? plantedAt,
    String placement = 'outdoor',
    String? plantingMaterial,
    int quantity = 1,
    String irrigationSchedule = 'every_3_5_days',
  }) async {
    final body = <String, dynamic>{
      'label': label,
      'variety': variety,
      'nursery_started_at': _formatDate(nurseryStartedAt),
      'placement': placement,
      'quantity': quantity,
      'irrigation_schedule': irrigationSchedule,
    };

    if (plantedAt != null) {
      body['planted_at'] = _formatDate(plantedAt);
    }

    if (plantingMaterial != null) {
      body['planting_material'] = plantingMaterial;
    }

    final response = await _apiClient.post(
      '${ApiConfig.baseUrl}/farms/$farmId/plants',
      body,
      requiresAuth: true,
    );

    final data = response['data'];

    if (data is! Map) {
      throw Exception(
        'Data tanaman dari server tidak valid.',
      );
    }

    return PlantModel.fromJson(
      Map<String, dynamic>.from(data),
    );
  }

  // FORMAT DATE: YYYY-MM-DD
  String _formatDate(DateTime date) {
    final year = date.year.toString();
    final month = date.month.toString().padLeft(2, '0');
    final day = date.day.toString().padLeft(2, '0');

    return '$year-$month-$day';
  }
}
