
class ApiConfig {
  static const String baseUrl =
      'http://127.0.0.1:8000/api/v1';

  static const String register =
      '$baseUrl/auth/register';

  static const String login =
      '$baseUrl/auth/login';

  static const String refresh =
      '$baseUrl/auth/refresh';

  static const String logout =
      '$baseUrl/auth/logout';
}
