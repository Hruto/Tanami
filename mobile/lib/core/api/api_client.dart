
import 'dart:convert';
import 'package:http/http.dart' as http;

class ApiClient {
  Future<Map<String, dynamic>> post(
    String endpoint,
    Map<String, dynamic> body,
  ) async {
    final url = Uri.parse(endpoint);

    final response = await http.post(
      url,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
      body: jsonEncode(body),
    );

    final responseBody = response.body.isNotEmpty
        ? jsonDecode(response.body)
        : null;

    if (response.statusCode >= 200 &&
        response.statusCode < 300) {
      if (responseBody is Map<String, dynamic>) {
        return responseBody;
      }

      return {};
    }

    String message = 'Terjadi kesalahan pada server.';

    if (responseBody is Map<String, dynamic>) {
      final error = responseBody['error'];

      if (error is Map<String, dynamic> &&
          error['message'] is String) {
        message = error['message'];
        }
    }

    throw Exception(message);
  }
}
