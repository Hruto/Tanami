
class UserModel {
  final String id;
  final String email;
  final String username;
  final String fullName;
  final String role;

  const UserModel({
    required this.id,
    required this.email,
    required this.username,
    required this.fullName,
    required this.role,
  });

  factory UserModel.fromJson(Map<String, dynamic> json) {
    return UserModel(
      id: json['id']?.toString() ?? '',
      email: json['email']?.toString() ?? '',
      username: json['username']?.toString() ?? '',
      fullName: json['full_name']?.toString() ?? 'Pengguna',
      role: json['role']?.toString() ?? '',
    );
  }
}
