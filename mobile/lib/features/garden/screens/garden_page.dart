
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';
import '../models/plant_model.dart';
import '../services/plant_service.dart';
import 'add_plant_page.dart';

import '../../../core/widget/harvest_plant_card.dart';

class GardenPage extends StatefulWidget {
  final String? farmId;

  const GardenPage({
    super.key,
    required this.farmId,
  });

  @override
  State<GardenPage> createState() => _GardenPageState();
}

class _GardenPageState extends State<GardenPage> {
  final PlantService _plantService = PlantService();

  final TextEditingController _searchController =
      TextEditingController();

  late Future<List<PlantModel>> _plantsFuture;

  String _searchQuery = '';

  static const String _crossIcon = 'assets/icons/cross.svg';
  static const String _searchIcon = 'assets/icons/search.svg';
  static const String _plusIcon = 'assets/icons/plus.svg';
  static const String _plantIcon = 'assets/icons/Tree_Palm.svg';
  static const String _cloudErrorIcon = 'assets/icons/cloud_error.svg';

  Widget _svgIcon(
    String path, {
    double size = 24,
    Color? color,
  }) {
    return SvgPicture.asset(
      path,
      width: size,
      height: size,
      fit: BoxFit.contain,
      colorFilter: color == null
          ? null
          : ColorFilter.mode(color, BlendMode.srcIn),
    );
  }

  @override
  void initState() {
    super.initState();
    _loadPlants();
  }

  @override
  void didUpdateWidget(covariant GardenPage oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (oldWidget.farmId != widget.farmId) {
      _loadPlants();
    }
  }

  void _loadPlants() {
    if (widget.farmId == null) {
      _plantsFuture = Future.value([]);
    } else {
      _plantsFuture = _plantService.getPlants(widget.farmId!);
    }
  }

  Future<void> _refreshPlants() async {
    setState(_loadPlants);
    await _plantsFuture;
  }

Future<void> _openAddPlantPage() async {
  if (widget.farmId == null) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Pilih kebun terlebih dahulu.'),
      ),
    );
    return;
  }

  final result = await Navigator.push<bool>(
    context,
    MaterialPageRoute(
      builder: (_) => AddPlantPage(
        farmId: widget.farmId,
      ),
    ),
  );

  if (!mounted) return;

  if (result == true) {
    setState(_loadPlants);
  }
}

  @override
  void dispose() {
    _searchController.dispose();
    super.dispose();
  }

  // Header hijau
  Widget _buildHeader() {
    return Container(
      height: 94,
      width: double.infinity,
      decoration: const BoxDecoration(
        color: AppColors.mediumGreen,
        borderRadius: BorderRadius.only(
          bottomLeft: Radius.circular(28),
          bottomRight: Radius.circular(28),
        ),
      ),
      child: SafeArea(
        bottom: false,
        child: Center(
          child: SvgPicture.asset(
            'assets/images/logo_header.svg',
            height: 35,
          ),
        ),
      ),
    );
  }

  // Search bar dan tombol tambah
  Widget _buildSearchBar() {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 20),
      child: Row(
        children: [
          Expanded(
            child: Container(
              height: 52,
              decoration: BoxDecoration(
                color: const Color(0xFFDDE3D9),
                borderRadius: BorderRadius.circular(30),
                boxShadow: [
                  BoxShadow(
                    color: Colors.black.withValues(alpha: 0.14),
                    blurRadius: 7,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: TextField(
                controller: _searchController,
                onChanged: (value) {
                  setState(() {
                    _searchQuery = value.toLowerCase();
                  });
                },
                decoration: InputDecoration(
                  hintText: 'Cari tanaman...',
                  hintStyle: const TextStyle(
                    fontSize: 12,
                    color: AppColors.grey,
                  ),
                  suffixIcon: _searchQuery.isNotEmpty
                      ? IconButton(
                          onPressed: () {
                            _searchController.clear();
                            setState(() {
                              _searchQuery = '';
                            });
                          },
                          icon: _svgIcon(
                            _crossIcon,
                            size: 20,
                            color: AppColors.grey,
                          ),
                        )
                      : Padding(
                          padding: const EdgeInsets.all(13),
                          child: _svgIcon(
                            _searchIcon,
                            size: 22,
                            color: AppColors.grey,
                          ),
                        ),
                  contentPadding: const EdgeInsets.symmetric(
                    horizontal: 18,
                    vertical: 15,
                  ),
                  border: InputBorder.none,
                ),
              ),
            ),
          ),

          const SizedBox(width: 10),

          Container(
            width: 54,
            height: 54,
            decoration: BoxDecoration(
              color: AppColors.grey,
              borderRadius: BorderRadius.circular(19),
              boxShadow: [
                BoxShadow(
                  color: Colors.black.withValues(alpha: 0.12),
                  blurRadius: 6,
                  offset: const Offset(0, 3),
                ),
              ],
            ),
            child: IconButton(
              onPressed: _openAddPlantPage,
              icon: _svgIcon(
                _plusIcon,
                size: 30,
                color: Colors.white,
              ),
            ),
          ),
        ],
      ),
    );
  }

  // Menghitung estimasi panen
  String _getHarvestText(PlantModel plant) {
    final harvestDate = plant.expectedHarvestMin;

    if (harvestDate == null || harvestDate.isEmpty) {
      return 'Estimasi panen belum tersedia';
    }

    try {
      final date = DateTime.parse(harvestDate);
      final today = DateTime.now();

      final difference = DateTime(
        date.year,
        date.month,
        date.day,
      ).difference(
        DateTime(today.year, today.month, today.day),
      ).inDays;

      if (difference < 0) {
        return 'Jadwal panen telah lewat';
      }

      if (difference == 0) {
        return 'Estimasi panen hari ini';
      }

      return 'Estimasi panen $difference hari lagi';
    } catch (_) {
      return 'Estimasi panen belum tersedia';
    }
  }

  // Mengubah placement menjadi teks
  String _getLocation(PlantModel plant) {
    if (plant.placement == 'indoor') {
      return 'Dalam Ruangan';
    }

    if (plant.placement == 'outdoor') {
      return 'Luar Ruangan';
    }

    return 'Lokasi belum tersedia';
  }

  // Menampilkan card tanaman
  Widget _buildPlantCard(PlantModel plant) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: HarvestPlantCard(
        name: plant.label.isNotEmpty
            ? plant.label
            : plant.displayName,
        location: _getLocation(plant),
        harvest: _getHarvestText(plant),
        maturity: plant.maturity,
        healthy: plant.isHealthy,
        iconAsset: _plantIcon,
        imageUrl: plant.coverPhotoUrl,
      ),
    );
  }

  // Empty state
  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: 35,
          vertical: 40,
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Text(
              'Belum Ada Tanaman',
              style: TextStyle(
                fontSize: 12,
                color: AppColors.grey,
              ),
            ),
          ],
        ),
      ),
    );
  }

  // Loading
  Widget _buildLoading() {
    return const Center(
      child: CircularProgressIndicator(
        color: AppColors.mediumGreen,
      ),
    );
  }

  // Error
  Widget _buildError() {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          _svgIcon(
            _cloudErrorIcon,
            size: 45,
            color: AppColors.grey,
          ),
          const SizedBox(height: 12),
          const Text(
            'Gagal memuat tanaman.',
            style: TextStyle(
              color: AppColors.darkGreen,
              fontWeight: FontWeight.w600,
            ),
          ),
          TextButton(
            onPressed: () {
              setState(_loadPlants);
            },
            child: const Text(
              'Coba Lagi',
              style: TextStyle(
                color: AppColors.mediumGreen,
              ),
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      color: AppColors.background,
      child: SafeArea(
        top: false,
        bottom: false,
        child: Column(
          children: [
            _buildHeader(),

            const SizedBox(height: 10),

            _buildSearchBar(),

            const SizedBox(height: 10),

            Expanded(
              child: FutureBuilder<List<PlantModel>>(
                future: _plantsFuture,
                builder: (context, snapshot) {
                  if (snapshot.connectionState ==
                      ConnectionState.waiting) {
                    return _buildLoading();
                  }

                  if (snapshot.hasError) {
                    return _buildError();
                  }

                  final plants = snapshot.data ?? [];

                  final filteredPlants = plants.where((plant) {
                    final name = plant.label.toLowerCase();
                    final commodity =
                        plant.commodityLabel.toLowerCase();
                    final variety =
                        (plant.variety ?? '').toLowerCase();

                    return name.contains(_searchQuery) ||
                        commodity.contains(_searchQuery) ||
                        variety.contains(_searchQuery);
                  }).toList();

                  if (plants.isEmpty) {
                    return RefreshIndicator(
                      color: AppColors.mediumGreen,
                      onRefresh: _refreshPlants,
                      child: ListView(
                        physics:
                            const AlwaysScrollableScrollPhysics(),
                        children: [
                          SizedBox(
                            height:
                                MediaQuery.of(context).size.height *
                                    0.48,
                            child: _buildEmptyState(),
                          ),
                        ],
                      ),
                    );
                  }

                  if (filteredPlants.isEmpty) {
                    return Center(
                      child: Text(
                        'Tanaman tidak ditemukan.',
                        style: TextStyle(
                          color: AppColors.grey,
                        ),
                      ),
                    );
                  }

                  return RefreshIndicator(
                    color: AppColors.mediumGreen,
                    onRefresh: _refreshPlants,
                    child: ListView.builder(
                      padding: const EdgeInsets.fromLTRB(
                        20,
                        0,
                        20,
                        110,
                      ),
                      physics:
                          const AlwaysScrollableScrollPhysics(),
                      itemCount: filteredPlants.length,
                      itemBuilder: (context, index) {
                        return _buildPlantCard(
                          filteredPlants[index],
                        );
                      },
                    ),
                  );
                },
              ),
            ),
          ],
        ),
      ),
    );
  }
}
