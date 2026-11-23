
import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;

import '../storage/token_storage.dart';

class ApiClient {
  // GET REQUEST
  Future<Map<String, dynamic>> get(
    String endpoint, {
    bool requiresAuth = true,
  }) async {
    final headers = await _buildHeaders(
      requiresAuth: requiresAuth,
    );

    final response = await http.get(
      Uri.parse(endpoint),
      headers: headers,
    );

    return _handleResponse(response);
  }

  // POST REQUEST
  Future<Map<String, dynamic>> post(
    String endpoint,
    Map<String, dynamic> body, {
    bool requiresAuth = true,
  }) async {
    final headers = await _buildHeaders(
      requiresAuth: requiresAuth,
    );

    final response = await http.post(
      Uri.parse(endpoint),
      headers: headers,
      body: jsonEncode(body),
    );

    return _handleResponse(response);
  }

  // BUILD HEADERS
  Future<Map<String, String>> _buildHeaders({
    required bool requiresAuth,
  }) async {
    final headers = <String, String>{
      'Content-Type': 'application/json',
      'Accept': 'application/json',
    };

    if (requiresAuth) {
      final accessToken = await TokenStorage.getAccessToken();

      debugPrint(
        'Access token tersedia: '
        '${accessToken != null && accessToken.isNotEmpty}',
      );

      if (accessToken == null || accessToken.isEmpty) {
        throw Exception(
          'Access token tidak ditemukan. Silakan login kembali.',
        );
      }

      headers['Authorization'] = 'Bearer $accessToken';
    }

    return headers;
  }

  // HANDLE RESPONSE
  Map<String, dynamic> _handleResponse(
    http.Response response,
  ) {
    dynamic responseBody;

    if (response.body.isNotEmpty) {
      try {
        responseBody = jsonDecode(response.body);
      } catch (_) {
        throw Exception(
          'Response server bukan JSON yang valid.',
        );
      }
    }

    if (response.statusCode >= 200 &&
        response.statusCode < 300) {
      if (response.statusCode == 204 ||
          response.body.isEmpty) {
        return {};
      }

      if (responseBody is Map<String, dynamic>) {
        return responseBody;
      }

      throw Exception(
        'Format response server tidak valid.',
      );
    }

    throw Exception(
      _getErrorMessage(responseBody),
    );
  }

  // ERROR MESSAGE
  String _getErrorMessage(dynamic responseBody) {
    if (responseBody is Map<String, dynamic>) {
      final error = responseBody['error'];

      if (error is Map<String, dynamic> &&
          error['message'] is String) {
        return error['message'];
      }

      final detail = responseBody['detail'];

      if (detail is String) {
        return detail;
      }

      if (detail is List) {
        return detail.map((item) {
          if (item is Map<String, dynamic>) {
            return item['msg']?.toString() ??
                item.toString();
          }

          return item.toString();
        }).join(', ');
      }

      if (responseBody['message'] is String) {
        return responseBody['message'];
      }
    }

    return 'Terjadi kesalahan pada server.';
  }
}
