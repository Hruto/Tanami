import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';

import '../models/farm_model.dart';
import '../models/region_model.dart';

class FarmService {
  final ApiClient _apiClient = ApiClient();

  // GET: Mengambil daftar kebun
  Future<List<FarmModel>> getFarms() async {
    final response = await _apiClient.get(
      '${ApiConfig.baseUrl}/farms?include_archived=false',
    );

    final data = response['data'];

    if (data is! List) {
      throw Exception('Format data Farms dari server tidak valid.');
    }

    return data
        .map(
          (item) => FarmModel.fromJson(
            item as Map<String, dynamic>,
          ),
        )
        .toList();
  }

  // GET: Mencari alamat/wilayah
  Future<List<RegionModel>> searchRegions(String query) async {
    if (query.trim().length < 2) {
      return [];
    }

    final uri = Uri.parse(
      '${ApiConfig.baseUrl}/regions/search',
    ).replace(
      queryParameters: {
        'q': query.trim(),
        'limit': '20',
      },
    );

    final response = await _apiClient.get(uri.toString());

    final data = response['data'];

    if (data is! List) {
      throw Exception('Format data Regions dari server tidak valid.');
    }

    return data
        .map(
          (item) => RegionModel.fromJson(
            item as Map<String, dynamic>,
          ),
        )
        .toList();
  }

  // POST: Membuat kebun baru
  // POST: Membuat kebun baru
  Future<FarmModel> createFarm({
    required String name,
    required String adm4Code,
  }) async {
    final response = await _apiClient.post(
      '${ApiConfig.baseUrl}/farms',
      {
        'name': name,
        'adm4_code': adm4Code,
      },
      requiresAuth: true,
    );

    final data = response['data'];

    if (data is! Map<String, dynamic>) {
      throw Exception('Data kebun dari server tidak valid.');
    }

    return FarmModel.fromJson(data);
  }}