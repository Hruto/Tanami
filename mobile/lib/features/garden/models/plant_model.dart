
class PlantModel {
  final String id;
  final String farmId;
  final String label;
  final String commodityLabel;
  final String? commodityCode;
  final String? variety;
  final String? healthStatus;
  final String? growthStage;
  final String? expectedHarvestMin;
  final String? expectedHarvestMax;
  final String? farmName;
  final String? village;
  final String? placement;
  final String? coverPhotoUrl;
  final String? plantedAt;
  final String? nurseryStartedAt;
  final String? productiveUntil;
  final String? irrigationSchedule;
  final String? nextWateringOn;
  final int ageDays;
  final int harvestCount;
  final String? status;

  const PlantModel({
    required this.id,
    required this.farmId,
    required this.label,
    required this.commodityLabel,
    this.commodityCode,
    this.variety,
    this.healthStatus,
    this.growthStage,
    this.expectedHarvestMin,
    this.expectedHarvestMax,
    this.farmName,
    this.village,
    this.placement,
    this.coverPhotoUrl,
    this.plantedAt,
    this.nurseryStartedAt,
    this.productiveUntil,
    this.irrigationSchedule,
    this.nextWateringOn,
    this.ageDays = 0,
    this.harvestCount = 0,
    this.status,
  });

  factory PlantModel.fromJson(Map<String, dynamic> json) {
    final nextHarvest = json['next_harvest'];

    return PlantModel(
      id: json['id']?.toString() ?? '',
      farmId: json['farm_id']?.toString() ?? '',
      label: json['label']?.toString() ?? '',
      commodityLabel:
          json['commodity_label']?.toString() ?? '',
      commodityCode:
          json['commodity_code']?.toString(),
      variety: json['variety']?.toString(),
      healthStatus: json['health_status']?.toString(),
      growthStage: json['lifecycle_phase']?.toString(),

      expectedHarvestMin:
          nextHarvest is Map<String, dynamic>
              ? nextHarvest['start']?.toString()
              : null,

      expectedHarvestMax:
          nextHarvest is Map<String, dynamic>
              ? nextHarvest['end']?.toString()
              : null,

      farmName: json['farm_name']?.toString(),
      village: json['village']?.toString(),
      placement: json['placement']?.toString(),
      coverPhotoUrl: json['cover_photo_url']?.toString(),
      plantedAt: json['planted_at']?.toString(),
      nurseryStartedAt:
          json['nursery_started_at']?.toString(),
      productiveUntil:
          json['productive_until']?.toString(),
      irrigationSchedule:
          json['irrigation_schedule']?.toString(),
      nextWateringOn:
          json['next_watering_on']?.toString(),
      ageDays: (json['age_days'] as num?)?.toInt() ?? 0,
      harvestCount:
          (json['harvest_count'] as num?)?.toInt() ?? 0,
      status: json['status']?.toString(),
    );
  }

  String get displayName {
    return commodityLabel.isNotEmpty
        ? commodityLabel
        : label;
  }

  bool get isHealthy {
    return healthStatus == 'healthy';
  }

  // Placeholder sementara karena PlantOut
  // belum menyediakan maturity percentage.
  int get maturity => 0;
}
