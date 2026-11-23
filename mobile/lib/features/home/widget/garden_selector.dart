
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';
import '../../garden/models/farm_model.dart';
import '../../garden/models/region_model.dart';
import '../../garden/services/farm_service.dart';

class GardenSelector extends StatefulWidget {
  final List<FarmModel> farms;
  final String? selectedFarmId;
  final ValueChanged<FarmModel>? onFarmCreated;
  final ValueChanged<FarmModel>? onFarmSelected;

  const GardenSelector({
    super.key,
    required this.farms,
    this.selectedFarmId,
    this.onFarmCreated,
    this.onFarmSelected,
  });

  @override
  State<GardenSelector> createState() => _GardenSelectorState();
}

class _GardenSelectorState extends State<GardenSelector> {
  final LayerLink _layerLink = LayerLink();
  final GlobalKey _selectorKey = GlobalKey();

  OverlayEntry? _dropdownEntry;

  late List<FarmModel> _farms;
  FarmModel? _selectedFarm;

  bool _isExpanded = false;

  @override
  void initState() {
    super.initState();

    _farms = List.from(widget.farms);
    _syncSelectedFarm();
  }

  @override
  void didUpdateWidget(covariant GardenSelector oldWidget) {
    super.didUpdateWidget(oldWidget);

    if (oldWidget.farms != widget.farms ||
        oldWidget.selectedFarmId != widget.selectedFarmId) {
      _farms = List.from(widget.farms);
      _syncSelectedFarm();
    }
  }

  // Pilihan kebun selalu mengikuti HomePage.
  void _syncSelectedFarm() {
    if (_farms.isEmpty) {
      _selectedFarm = null;
      return;
    }

    final selectedId = widget.selectedFarmId;

    _selectedFarm = _farms.firstWhere(
      (farm) => farm.id == selectedId,
      orElse: () => _farms.first,
    );
  }

  void _toggleDropdown() {
    if (_farms.isEmpty) {
      _showAddGardenSheet();
      return;
    }

    if (_isExpanded) {
      _closeDropdown();
    } else {
      _showDropdown();
    }
  }

  void _showDropdown() {
    if (_dropdownEntry != null) return;

    final selectorContext = _selectorKey.currentContext;
    if (selectorContext == null) return;

    final renderBox =
        selectorContext.findRenderObject() as RenderBox;

    final width = renderBox.size.width;

    _dropdownEntry = OverlayEntry(
      builder: (overlayContext) {
        return Stack(
          children: [
            Positioned.fill(
              child: GestureDetector(
                behavior: HitTestBehavior.translucent,
                onTap: _closeDropdown,
                child: const SizedBox.expand(),
              ),
            ),
            CompositedTransformFollower(
              link: _layerLink,
              showWhenUnlinked: false,
              targetAnchor: Alignment.bottomLeft,
              followerAnchor: Alignment.topLeft,
              child: Material(
                color: Colors.transparent,
                child: SizedBox(
                  width: width,
                  child: Container(
                    decoration: const BoxDecoration(
                      color: AppColors.fieldBackground,
                      borderRadius: BorderRadius.only(
                        bottomLeft: Radius.circular(22),
                        bottomRight: Radius.circular(22),
                      ),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        for (final farm in _farms)
                          if (farm.id != _selectedFarm?.id)
                            _buildGardenOption(farm),
                        const Divider(
                          height: 1,
                          thickness: 0.5,
                          color: AppColors.grey,
                        ),
                        _buildAddGardenOption(),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ],
        );
      },
    );

    Overlay.of(context, rootOverlay: true)
        .insert(_dropdownEntry!);

    setState(() {
      _isExpanded = true;
    });
  }

  void _closeDropdown() {
    _dropdownEntry?.remove();
    _dropdownEntry = null;

    if (mounted && _isExpanded) {
      setState(() {
        _isExpanded = false;
      });
    }
  }

  Widget _buildGardenOption(FarmModel farm) {
    return InkWell(
      onTap: () {
        _closeDropdown();

        // Pilihan diubah oleh HomePage.
        widget.onFarmSelected?.call(farm);
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: 25,
          vertical: 11,
        ),
        child: Row(
          children: [
            SvgPicture.asset(
              'assets/icons/tree_outline.svg',
              width: 25,
              height: 25,
            ),
            const SizedBox(width: 18),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    farm.name,
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(
                      color: AppColors.darkGreen,
                      fontSize: 15,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  Text(
                    farm.village ?? '',
                    style: const TextStyle(
                      color: AppColors.grey,
                      fontSize: 11,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAddGardenOption() {
    return InkWell(
      onTap: () {
        _closeDropdown();
        _showAddGardenSheet();
      },
      child: Padding(
        padding: const EdgeInsets.symmetric(
          horizontal: 25,
          vertical: 12,
        ),
        child: Row(
          children: [
            SvgPicture.asset(
              'assets/icons/tree_plus.svg',
              width: 25,
              height: 25,
            ),
            const SizedBox(width: 18),
            const Text(
              'Tambah Kebun',
              style: TextStyle(
                color: AppColors.darkGreen,
                fontSize: 15,
                fontWeight: FontWeight.w700,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _showAddGardenSheet() async {
    final newFarm = await showModalBottomSheet<FarmModel>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => const AddGardenBottomSheet(),
    );

    if (newFarm == null || !mounted) return;

    // Pilihan kebun baru dikirim ke HomePage.
    widget.onFarmCreated?.call(newFarm);
  }

  @override
  void dispose() {
    _dropdownEntry?.remove();
    _dropdownEntry = null;
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final hasGarden = _selectedFarm != null;

    return CompositedTransformTarget(
      link: _layerLink,
      child: GestureDetector(
        onTap: hasGarden ? null : _toggleDropdown,
        child: Container(
          key: _selectorKey,
          padding: const EdgeInsets.symmetric(
            horizontal: 20,
            vertical: 12,
          ),
          decoration: BoxDecoration(
            color: AppColors.background,
            borderRadius: BorderRadius.vertical(
              top: const Radius.circular(22),
              bottom: Radius.circular(
                _isExpanded ? 0 : 22,
              ),
            ),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withOpacity(0.15),
                blurRadius: 8,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          child: Row(
            children: [
              if (hasGarden)
                SvgPicture.asset(
                  'assets/icons/tree_filled.svg',
                  width: 25,
                  height: 25,
                )
              else
                SvgPicture.asset(
                  'assets/icons/tree_plus.svg',
                  width: 25,
                  height: 25,
                ),
              const SizedBox(width: 18),
              Expanded(
                child: hasGarden
                    ? Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _selectedFarm!.name,
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                            style: const TextStyle(
                              color: AppColors.darkGreen,
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                            ),
                          ),
                          Text(
                            _selectedFarm!.village ?? '',
                            style: const TextStyle(
                              color: AppColors.grey,
                              fontSize: 11,
                            ),
                          ),
                        ],
                      )
                    : const Text(
                        'Tambah Kebun',
                        style: TextStyle(
                          color: AppColors.darkGreen,
                          fontSize: 15,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
              ),
              if (hasGarden)
                IconButton(
                  onPressed: _toggleDropdown,
                  icon: Icon(
                    _isExpanded
                        ? Icons.keyboard_arrow_up_rounded
                        : Icons.keyboard_arrow_down_rounded,
                    color: AppColors.darkGreen,
                    size: 26,
                  ),
                ),
            ],
          ),
        ),
      ),
    );
  }
}

// ======================================================
// BOTTOM SHEET TAMBAH KEBUN
// ======================================================

class AddGardenBottomSheet extends StatefulWidget {
  const AddGardenBottomSheet({super.key});

  @override
  State<AddGardenBottomSheet> createState() =>
      _AddGardenBottomSheetState();
}

class _AddGardenBottomSheetState extends State<AddGardenBottomSheet> {
  final FarmService _farmService = FarmService();

  final TextEditingController _nameController =
      TextEditingController();

  final TextEditingController _addressController =
      TextEditingController();

  List<RegionModel> _regions = [];

  RegionModel? _selectedRegion;

  bool _isSearching = false;
  bool _isSaving = false;
  bool _showSuggestions = false;

  Future<void> _searchRegions(String query) async {
    setState(() {
      _selectedRegion = null;
      _showSuggestions = query.trim().length >= 2;
    });

    if (query.trim().length < 2) {
      setState(() {
        _regions = [];
        _isSearching = false;
      });
      return;
    }

    setState(() {
      _isSearching = true;
    });

    try {
      final results = await _farmService.searchRegions(query);

      if (!mounted) return;

      // Abaikan hasil pencarian lama jika teks sudah berubah.
      if (_addressController.text.trim() != query.trim()) return;

      setState(() {
        _regions = results;
        _isSearching = false;
      });
    } catch (e) {
      if (!mounted) return;

      setState(() {
        _regions = [];
        _isSearching = false;
      });
    }
  }

  void _selectRegion(RegionModel region) {
    setState(() {
      _selectedRegion = region;
      _addressController.text = region.fullAddress;
      _showSuggestions = false;
      _regions = [];
    });

    FocusScope.of(context).unfocus();
  }

  Future<void> _saveFarm() async {
    final name = _nameController.text.trim();

    if (name.isEmpty) {
      _showMessage('Nama kebun wajib diisi.');
      return;
    }

    if (_selectedRegion == null) {
      _showMessage('Pilih alamat dari hasil pencarian terlebih dahulu.');
      return;
    }

    setState(() {
      _isSaving = true;
    });

    try {
      final newFarm = await _farmService.createFarm(
        name: name,
        adm4Code: _selectedRegion!.adm4Code,
      );

      if (!mounted) return;

      Navigator.pop(context, newFarm);
    } catch (e) {
      if (!mounted) return;

      _showMessage(e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) {
        setState(() {
          _isSaving = false;
        });
      }
    }
  }

  void _showMessage(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message)),
    );
  }

  Widget _buildInput({
    required TextEditingController controller,
    required String hint,
    required Widget icon,
    void Function(String)? onChanged,
    bool readOnly = false,
  }) {
    return TextField(
      controller: controller,
      readOnly: readOnly,
      onChanged: onChanged,
      style: const TextStyle(
        color: AppColors.darkGreen,
        fontSize: 14,
      ),
      decoration: InputDecoration(
        hintText: hint,
        hintStyle: const TextStyle(
          color: AppColors.mediumGreen,
          fontSize: 14,
        ),
        prefixIcon: icon,
        filled: true,
        fillColor: AppColors.fieldBackground,
        contentPadding: const EdgeInsets.symmetric(
          horizontal: 16,
          vertical: 18,
        ),
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: BorderSide.none,
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: BorderSide.none,
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(18),
          borderSide: const BorderSide(
            color: AppColors.mediumGreen,
            width: 1,
          ),
        ),
      ),
    );
  }

  @override
  void dispose() {
    _nameController.dispose();
    _addressController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedPadding(
      duration: const Duration(milliseconds: 150),
      curve: Curves.easeOut,
      padding: EdgeInsets.only(
        bottom: MediaQuery.of(context).viewInsets.bottom,
      ),
      child: Container(
        width: double.infinity,
        constraints: BoxConstraints(
          maxHeight: MediaQuery.of(context).size.height * 0.85,
        ),
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        decoration: const BoxDecoration(
          color: AppColors.background,
          borderRadius: BorderRadius.vertical(
            top: Radius.circular(24),
          ),
        ),
        child: SingleChildScrollView(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            mainAxisSize: MainAxisSize.min,
            children: [
              Align(
                alignment: Alignment.centerRight,
                child: IconButton(
                  onPressed: () => Navigator.pop(context),
                  icon: const Icon(
                    Icons.close,
                    color: AppColors.mediumGreen,
                    size: 24,
                  ),
                ),
              ),
              const Center(
                child: Text(
                  'Tambah Kebun Baru',
                  style: TextStyle(
                    color: AppColors.darkGreen,
                    fontSize: 20,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
              const SizedBox(height: 28),

              const Text(
                'Nama Kebun',
                style: TextStyle(
                  color: AppColors.darkGreen,
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 8),

              _buildInput(
                controller: _nameController,
                hint: 'Kebun A',
                icon: Padding(
                  padding: const EdgeInsets.all(13),
                  child: SvgPicture.asset(
                    'assets/icons/tree_outline.svg',
                    width: 22,
                    height: 22,
                  ),
                ),
              ),

              const SizedBox(height: 14),

              const Text(
                'Alamat Kebun',
                style: TextStyle(
                  color: AppColors.darkGreen,
                  fontSize: 15,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 8),

              _buildInput(
                controller: _addressController,
                hint: 'Kec, Kab/Kota, Provinsi',
                onChanged: _searchRegions,
                icon: const Icon(
                  Icons.location_on_outlined,
                  color: AppColors.mediumGreen,
                  size: 22,
                ),
              ),

              if (_isSearching)
                const Padding(
                  padding: EdgeInsets.all(12),
                  child: Center(
                    child: CircularProgressIndicator(
                      color: AppColors.mediumGreen,
                    ),
                  ),
                ),

              if (_showSuggestions && !_isSearching)
                Container(
                  margin: const EdgeInsets.only(top: 6),
                  constraints: const BoxConstraints(maxHeight: 180),
                  decoration: BoxDecoration(
                    color: AppColors.background,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: AppColors.fieldBackground,
                    ),
                  ),
                  child: _regions.isEmpty
                      ? const Padding(
                          padding: EdgeInsets.all(12),
                          child: Text(
                            'Wilayah tidak ditemukan.',
                            style: TextStyle(
                              color: AppColors.grey,
                              fontSize: 13,
                            ),
                          ),
                        )
                      : ListView.separated(
                          shrinkWrap: true,
                          itemCount: _regions.length,
                          separatorBuilder: (_, __) =>
                              const Divider(height: 1),
                          itemBuilder: (context, index) {
                            final region = _regions[index];

                            return ListTile(
                              dense: true,
                              title: Text(
                                region.village,
                                style: const TextStyle(
                                  color: AppColors.darkGreen,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              subtitle: Text(
                                region.fullAddress,
                                style: const TextStyle(
                                  color: AppColors.grey,
                                  fontSize: 11,
                                ),
                              ),
                              onTap: () => _selectRegion(region),
                            );
                          },
                        ),
                ),

              const SizedBox(height: 20),

              SizedBox(
                width: double.infinity,
                height: 60,
                child: ElevatedButton(
                  onPressed: _isSaving ? null : _saveFarm,
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.mediumGreen,
                    foregroundColor: Colors.white,
                    disabledBackgroundColor:
                        AppColors.mediumGreen.withOpacity(0.6),
                    elevation: 0,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(18),
                    ),
                  ),
                  child: _isSaving
                      ? const SizedBox(
                          width: 24,
                          height: 24,
                          child: CircularProgressIndicator(
                            color: Colors.white,
                            strokeWidth: 2,
                          ),
                        )
                      : const Text(
                          'Simpan',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}