class WeatherModel {
  final List<WeatherDayModel> days;

  const WeatherModel({required this.days});

  factory WeatherModel.fromJson(Map<String, dynamic> json) {
    return WeatherModel(
      days: (json['days'] as List? ?? [])
          .map((item) => WeatherDayModel.fromJson(
                item as Map<String, dynamic>,
              ))
          .toList(),
    );
  }

  WeatherSlotModel? get currentSlot {
    final slots = days.expand((day) => day.slots).toList();

    if (slots.isEmpty) return null;

    final now = DateTime.now();

    final upcoming = slots.where((slot) {
      return !slot.dateTime.isBefore(now);
    }).toList();

    if (upcoming.isNotEmpty) {
      return upcoming.first;
    }

    return slots.first;
  }
}

class WeatherDayModel {
  final String date;
  final List<WeatherSlotModel> slots;

  const WeatherDayModel({
    required this.date,
    required this.slots,
  });

  factory WeatherDayModel.fromJson(Map<String, dynamic> json) {
    return WeatherDayModel(
      date: json['date'] ?? '',
      slots: (json['slots'] as List? ?? [])
          .map((item) => WeatherSlotModel.fromJson(
                item as Map<String, dynamic>,
              ))
          .toList(),
    );
  }
}

class WeatherSlotModel {
  final String localDateTime;
  final double? temperature;
  final double? humidity;
  final String weatherDescription;

  const WeatherSlotModel({
    required this.localDateTime,
    this.temperature,
    this.humidity,
    required this.weatherDescription,
  });

  DateTime get dateTime {
    return DateTime.tryParse(localDateTime) ?? DateTime.now();
  }

  factory WeatherSlotModel.fromJson(Map<String, dynamic> json) {
    return WeatherSlotModel(
      localDateTime: json['local_datetime'] ?? '',
      temperature: (json['t'] as num?)?.toDouble(),
      humidity: (json['hu'] as num?)?.toDouble(),
      weatherDescription: json['weather_desc'] ?? '-',
    );
  }
}