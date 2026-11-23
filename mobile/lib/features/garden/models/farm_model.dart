
class FarmModel {
  final String id;
  final String name;
  final String? adm4Code;
  final double? lat;
  final double? lon;
  final double? areaM2;
  final String? village;
  final int plantCount;
  final String? archivedAt;
  final String? createdAt;
  final String? updatedAt;

  const FarmModel({
    required this.id,
    required this.name,
    this.adm4Code,
    this.lat,
    this.lon,
    this.areaM2,
    this.village,
    this.plantCount = 0,
    this.archivedAt,
    this.createdAt,
    this.updatedAt,
  });

  factory FarmModel.fromJson(Map<String, dynamic> json) {
    return FarmModel(
      id: json['id'] ?? '',
      name: json['name'] ?? '',
      adm4Code: json['adm4_code'],
      lat: (json['lat'] as num?)?.toDouble(),
      lon: (json['lon'] as num?)?.toDouble(),
      areaM2: (json['area_m2'] as num?)?.toDouble(),
      village: json['village'],
      plantCount: json['plant_count'] ?? 0,
      archivedAt: json['archived_at'],
      createdAt: json['created_at'],
      updatedAt: json['updated_at'],
    );
  }
}
