
class HomeModel {
  final Map<String, dynamic>? weather;
  final List<dynamic> reminders;
  final List<dynamic> plantsNeedingAttention;
  final int unreadReminderCount;

  const HomeModel({
    this.weather,
    this.reminders = const [],
    this.plantsNeedingAttention = const [],
    this.unreadReminderCount = 0,
  });

  factory HomeModel.fromJson(Map<String, dynamic> json) {
    return HomeModel(
      weather: json['weather'] is Map<String, dynamic>
          ? json['weather'] as Map<String, dynamic>
          : null,
      reminders: json['reminders'] as List<dynamic>? ?? [],
      plantsNeedingAttention:
          json['plants_needing_attention'] as List<dynamic>? ?? [],
      unreadReminderCount:
          json['unread_reminder_count'] as int? ?? 0,
    );
  }
}
