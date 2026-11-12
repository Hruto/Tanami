
class LoginRequest {
  final String? email;
  final String? username;
  final String password;

  LoginRequest({
    this.email,
    this.username,
    required this.password,
  });

  Map<String, dynamic> toJson() {
    return {
      if (email != null) 'email': email,
      if (username != null) 'username': username,
      'password': password,
    };
  }
}
