class RegionModel {
  final String adm4Code;
  final String village;
  final String district;
  final String regency;
  final String province;

  const RegionModel({
    required this.adm4Code,
    required this.village,
    required this.district,
    required this.regency,
    required this.province,
  });

  factory RegionModel.fromJson(Map<String, dynamic> json) {
    return RegionModel(
      adm4Code: json['adm4_code'] ?? '',
      village: json['village'] ?? '',
      district: json['district'] ?? '',
      regency: json['regency'] ?? '',
      province: json['province'] ?? '',
    );
  }

  String get fullAddress {
    return '$district, $regency, $province';
  }
}