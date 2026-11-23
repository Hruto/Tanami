
class PlantSummaryModel {
  final int total;
  final int healthy;
  final int sick;

  const PlantSummaryModel({
    required this.total,
    required this.healthy,
    required this.sick,
  });

  int get healthyPercent {
    if (total == 0) return 0;
    return ((healthy / total) * 100).round();
  }

  int get sickPercent {
    if (total == 0) return 0;
    return ((sick / total) * 100).round();
  }
}
