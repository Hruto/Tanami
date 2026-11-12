
class RegisterRequest {
  final String email;
  final String username;
  final String fullName;
  final String password;
  final bool consentTrainingData;

  RegisterRequest({
    required this.email,
    required this.username,
    required this.fullName,
    required this.password,
    this.consentTrainingData = false,
  });

  Map<String, dynamic> toJson() {
    return {
      'email': email,
      'username': username,
      'full_name': fullName,
      'password': password,
      'consent_training_data': consentTrainingData,
    };
  }
}
