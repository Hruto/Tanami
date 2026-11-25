import 'dart:typed_data';

import 'package:http/http.dart' as http;

import '../../../core/api/api_client.dart';
import '../../../core/api/api_config.dart';
import '../models/plant_model.dart';
import 'package:flutter/foundation.dart';

class PlantService {
  final ApiClient _apiClient = ApiClient();

  /// Mengambil daftar tanaman berdasarkan status tracking.
  /// active = tanaman yang masih dilacak, ended = riwayat tracking.
  Future<List<PlantModel>> getPlants(
    String farmId, {
    String status = 'active',
  }) async {
    if (status != 'active' && status != 'ended') {
      throw ArgumentError.value(status, 'status', 'Harus active atau ended.');
    }

    final response = await _apiClient.get(
      '${ApiConfig.baseUrl}/farms/$farmId/plants?status=$status',
    );

    final data = response['data'];
    if (data is! List) {
      throw Exception('Format data tanaman dari server tidak valid.');
    }

    return data.map((item) {
      return PlantModel.fromJson(Map<String, dynamic>.from(item));
    }).toList();
  }

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

    debugPrint('Request body create plant: $body');

    final response = await _apiClient.post(
      '${ApiConfig.baseUrl}/farms/$farmId/plants',
      body,
      requiresAuth: true,
    );

    final data = response['data'];
    if (data is! Map) {
      throw Exception('Data tanaman dari server tidak valid.');
    }

    return PlantModel.fromJson(Map<String, dynamic>.from(data));
  }

  Future<Map<String, dynamic>> uploadPlantPhoto({
    required String plantId,
    required Uint8List imageBytes,
    required String fileName,
    String? caption,
    DateTime? takenAt,
  }) async {
    final fields = <String, String>{};

    if (caption != null && caption.trim().isNotEmpty) {
      fields['caption'] = caption.trim();
    }

    if (takenAt != null) {
      fields['taken_at'] = _formatDate(takenAt);
    }

    return _apiClient.uploadFile(
      endpoint: '${ApiConfig.baseUrl}/plants/$plantId/photos',
      file: http.MultipartFile.fromBytes(
        'image',
        imageBytes,
        filename: fileName,
      ),
      fields: fields,
      requiresAuth: true,
    );
  }

  String _formatDate(DateTime date) {
    final year = date.year.toString();
    final month = date.month.toString().padLeft(2, '0');
    final day = date.day.toString().padLeft(2, '0');
    return '$year-$month-$day';
  }
}
