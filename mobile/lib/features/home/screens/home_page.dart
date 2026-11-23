
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/constant/app_colors.dart';
import '../../../shared/bottom_nav_bar.dart';

import '../models/home_model.dart';

import '../services/home_service.dart';
import '../services/user_service.dart';

import '../../garden/models/farm_model.dart';
import '../../garden/models/plant_model.dart';
import '../../garden/services/farm_service.dart';
import '../../garden/services/plant_service.dart';
import '../../garden/screens/garden_page.dart';

import '../widget/home_header.dart';
import '../widget/garden_selector.dart';
import '../widget/weather_card.dart';
import '../widget/plant_summary_card.dart';
import '../widget/harvest_plant_card.dart';
import '../../profile/screens/profile_page.dart';

// Penampung data Home dan Farms
class _DashboardData {
  final HomeModel home;
  final List<FarmModel> farms;

  const _DashboardData({
    required this.home,
    required this.farms,
  });
}

class HomePage extends StatefulWidget {
  const HomePage({super.key});

  @override
  State<HomePage> createState() => _HomePageState();
}

class _HomePageState extends State<HomePage> {
  final UserService _userService = UserService();
  final HomeService _homeService = HomeService();
  final FarmService _farmService = FarmService();
  final PlantService _plantService = PlantService();

  String _userName = 'Pengguna';

  String? _selectedFarmId;

  int _selectedIndex = 0;

  late Future<_DashboardData> _dashboardFuture;
  Future<List<PlantModel>>? _plantsFuture;

  @override
  void initState() {
    super.initState();

    _dashboardFuture = _loadDashboard();
    _loadUserProfile();
  }

  // Mengambil profil pengguna yang sedang login
  Future<void> _loadUserProfile() async {
    try {
      final user = await _userService.getCurrentUser();

      if (!mounted) return;

      setState(() {
        _userName = user.fullName.isNotEmpty
            ? user.fullName
            : 'Pengguna';
      });
    } catch (e) {
      debugPrint('Gagal mengambil profil pengguna: $e');
    }
  }

  // Mengambil data Home, Farms, dan Plants

Future<_DashboardData> _loadDashboard({
  String? preferredFarmId,
}) async {
  final homeData = await _homeService.getHomeData();
  final farmsData = await _farmService.getFarms();

  final prefs = await SharedPreferences.getInstance();

  final savedFarmId =
      preferredFarmId ?? prefs.getString('selected_farm_id');

  if (farmsData.isNotEmpty) {
    final selectedFarm = farmsData.firstWhere(
      (farm) => farm.id == savedFarmId,
      orElse: () => farmsData.first,
    );

    _selectedFarmId = selectedFarm.id;

    await prefs.setString(
      'selected_farm_id',
      selectedFarm.id,
    );

    _plantsFuture = _plantService.getPlants(selectedFarm.id);
  } else {
    _selectedFarmId = null;
    _plantsFuture = Future.value([]);

    await prefs.remove('selected_farm_id');
  }

  return _DashboardData(
    home: homeData,
    farms: farmsData,
  );
}


  // Mengambil ulang data dashboard

void _retryFetchData() {
  setState(() {
    _dashboardFuture = _loadDashboard(
      preferredFarmId: _selectedFarmId,
    );
  });
}


  // Mengganti kebun dan memperbarui data tanaman


void _onFarmSelected(FarmModel farm) {
  if (_selectedFarmId == farm.id) return;

  setState(() {
    _selectedFarmId = farm.id;
    _plantsFuture = _plantService.getPlants(farm.id);
  });

  _saveSelectedFarm(farm.id);
}



Future<void> _onFarmCreated(FarmModel farm) async {
  await _saveSelectedFarm(farm.id);

  if (!mounted) return;

  setState(() {
    _selectedFarmId = farm.id;
    _plantsFuture = _plantService.getPlants(farm.id);

    _dashboardFuture = _loadDashboard(
      preferredFarmId: farm.id,
    );
  });
}


Future<void> _saveSelectedFarm(String farmId) async {
  final prefs = await SharedPreferences.getInstance();

  await prefs.setString('selected_farm_id', farmId);
}


  // Navigasi Bottom Navigation
  void _onNavigationTap(int index) {
    if (index == 0 || index == 1 || index == 4) {
      setState(() {
        _selectedIndex = index;
      });

      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
          '${BottomNavBar.labels[index]} sedang disiapkan.',
        ),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  // Mengubah tanggal estimasi panen menjadi teks
  String _getHarvestEstimate(PlantModel plant) {
    final harvestDate = DateTime.tryParse(
      plant.expectedHarvestMin ?? '',
    );

    if (harvestDate == null) {
      return 'Estimasi panen belum tersedia';
    }

    final today = DateTime.now();

    final todayDate = DateTime(
      today.year,
      today.month,
      today.day,
    );

    final targetDate = DateTime(
      harvestDate.year,
      harvestDate.month,
      harvestDate.day,
    );

    final difference = targetDate.difference(todayDate).inDays;

    if (difference < 0) {
      return 'Estimasi panen telah lewat';
    }

    if (difference == 0) {
      return 'Estimasi panen hari ini';
    }

    return 'Estimasi panen $difference hari lagi';
  }

  // Mengubah placement menjadi label
  String _getPlantLocation(String? placement) {
    switch (placement) {
      case 'indoor':
        return 'Dalam Ruangan';
      case 'outdoor':
        return 'Luar Ruangan';
      default:
        return 'Lokasi tidak tersedia';
    }
  }

  // Menampilkan daftar tanaman
  Widget _buildHarvestPlants() {
    if (_selectedFarmId == null || _plantsFuture == null) {
      return const Text(
        'Belum ada kebun yang dipilih.',
        style: TextStyle(
          fontSize: 12,
          color: AppColors.grey,
        ),
      );
    }

    return FutureBuilder<List<PlantModel>>(
      // Key dibuat unik agar tidak bentrok dengan WeatherCard.
      key: ValueKey('harvest-plants-$_selectedFarmId'),
      future: _plantsFuture,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Center(
            child: Padding(
              padding: EdgeInsets.all(20),
              child: CircularProgressIndicator(
                color: AppColors.mediumGreen,
              ),
            ),
          );
        }

        if (snapshot.hasError) {
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Gagal mengambil data tanaman.',
                style: TextStyle(
                  fontSize: 12,
                  color: AppColors.red,
                ),
              ),
              TextButton(
                onPressed: () {
                  setState(() {
                    _plantsFuture = _plantService.getPlants(
                      _selectedFarmId!,
                    );
                  });
                },
                child: const Text('Coba Lagi'),
              ),
            ],
          );
        }

        final plants = snapshot.data ?? [];

        if (plants.isEmpty) {
          return const Padding(
            padding: EdgeInsets.symmetric(vertical: 12),
            child: Text(
              'Belum ada tanaman di kebun ini.',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.grey,
              ),
            ),
          );
        }

        final sortedPlants = List<PlantModel>.from(plants);

        sortedPlants.sort((a, b) {
          final dateA = DateTime.tryParse(
            a.expectedHarvestMin ?? '',
          );

          final dateB = DateTime.tryParse(
            b.expectedHarvestMin ?? '',
          );

          if (dateA == null && dateB == null) return 0;
          if (dateA == null) return 1;
          if (dateB == null) return -1;

          return dateA.compareTo(dateB);
        });

        return Column(
          children: sortedPlants.map((plant) {
            return Padding(
              padding: const EdgeInsets.only(bottom: 12),
              child: HarvestPlantCard(
                name: plant.displayName,
                location: _getPlantLocation(plant.placement),
                harvest: _getHarvestEstimate(plant),
                maturity: null,
                healthy: plant.isHealthy,
                iconAsset: 'assets/icons/Tree_Palm.svg',
                imageUrl: plant.coverPhotoUrl,
              ),
            );
          }).toList(),
        );
      },
    );
  }

  // Dashboard setelah data berhasil diterima
  Widget _buildHomeBody(_DashboardData dashboard) {
    final selectedFarm = dashboard.farms.isEmpty
        ? null
        : dashboard.farms.firstWhere(
            (farm) => farm.id == _selectedFarmId,
            orElse: () => dashboard.farms.first,
          );

// Jika tab Kebun dipilih
    if (_selectedIndex == 1) {
      return GardenPage(
        key: ValueKey('garden-page-${selectedFarm?.id}'),
        farmId: selectedFarm?.id,
      );
    }

    // Jika tab Profile dipilih
    if (_selectedIndex == 4) {
      return const ProfilePage();
    }


    return Stack(
      children: [
        Container(
          height: 355,
          decoration: const BoxDecoration(
            color: AppColors.mediumGreen,
            borderRadius: BorderRadius.only(
              bottomLeft: Radius.circular(35),
              bottomRight: Radius.circular(35),
            ),
          ),
        ),

        SafeArea(
          bottom: false,
          child: SingleChildScrollView(
            padding: const EdgeInsets.only(
              left: 20,
              right: 20,
              top: 8,
              bottom: 110,
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                HomeHeader(
                  userName: _userName,
                ),

                const SizedBox(height: 18),

                GardenSelector(
                farms: dashboard.farms,
                selectedFarmId: _selectedFarmId,
                onFarmSelected: _onFarmSelected,
                onFarmCreated: _onFarmCreated,
              ),

                const SizedBox(height: 16),

                WeatherCard(
                  key: ValueKey(
                    'weather-card-${selectedFarm?.id}',
                  ),
                  farmId: selectedFarm?.id,
                  location: selectedFarm?.village,
                ),

                const SizedBox(height: 12),

                PlantSummaryCard(
                  key: ValueKey(
                    'summary-card-${selectedFarm?.id}',
                  ),
                  farmId: selectedFarm?.id,
                ),

                const SizedBox(height: 24),

                const Text(
                  'Mendekati Waktu Panen',
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    color: AppColors.darkGreen,
                  ),
                ),

                const SizedBox(height: 12),

                _buildHarvestPlants(),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // Tampilan loading dashboard
  Widget _buildLoading() {
    return const Center(
      child: CircularProgressIndicator(
        color: AppColors.mediumGreen,
      ),
    );
  }

  // Tampilan ketika API dashboard gagal
  Widget _buildError(Object error) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.cloud_off_outlined,
              size: 48,
              color: AppColors.grey,
            ),

            const SizedBox(height: 16),

            const Text(
              'Gagal mengambil data dashboard',
              textAlign: TextAlign.center,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w700,
                color: AppColors.darkGreen,
              ),
            ),

            const SizedBox(height: 8),

            Text(
              error.toString(),
              textAlign: TextAlign.center,
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.grey,
              ),
            ),

            const SizedBox(height: 16),

            ElevatedButton(
              onPressed: _retryFetchData,
              style: ElevatedButton.styleFrom(
                backgroundColor: AppColors.mediumGreen,
                foregroundColor: Colors.white,
              ),
              child: const Text('Coba Lagi'),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      extendBody: true,
      body: FutureBuilder<_DashboardData>(
        future: _dashboardFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting) {
            return _buildLoading();
          }

          if (snapshot.hasError) {
            return _buildError(snapshot.error!);
          }

          if (snapshot.hasData) {
            return _buildHomeBody(snapshot.data!);
          }

          return const Center(
            child: Text('Data dashboard belum tersedia'),
          );
        },
      ),
      bottomNavigationBar: BottomNavBar(
        currentIndex: _selectedIndex,
        onTap: _onNavigationTap,
      ),
    );
  }
}
