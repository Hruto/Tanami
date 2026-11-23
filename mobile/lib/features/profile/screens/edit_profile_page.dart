
import 'package:flutter/material.dart';
import 'package:flutter_svg/flutter_svg.dart';

import '../../../core/constant/app_colors.dart';
import '../../../shared/bottom_nav_bar.dart';

class EditProfilePage extends StatefulWidget {
  final String initialName;

  const EditProfilePage({
    super.key,
    required this.initialName,
  });

  @override
  State<EditProfilePage> createState() => _EditProfilePageState();
}

class _EditProfilePageState extends State<EditProfilePage> {
  late TextEditingController nameController;

  @override
  void initState() {
    super.initState();

    nameController = TextEditingController(
      text: widget.initialName,
    );
  }

  @override
  void dispose() {
    nameController.dispose();
    super.dispose();
  }

  // SVG ICON

Widget _svgIcon(
  String name, {
  double size = 24,
  Color color = AppColors.mediumGreen,
}) {
  return SvgPicture.asset(
    'assets/icons/$name.svg',
    width: size,
    height: size,
    fit: BoxFit.contain,
    colorFilter: ColorFilter.mode(
      color,
      BlendMode.srcIn,
    ),
  );
}


  // DEFAULT PROFILE PICTURE
  Widget _profilePicture() {
    return Stack(
      clipBehavior: Clip.none,
      children: [
        Container(
          width: 135,
          height: 135,
          padding: const EdgeInsets.all(5),
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            color: AppColors.mediumGreen,
          ),
          child: ClipOval(
            child: Container(
              color: AppColors.lightGreen,
              padding: const EdgeInsets.all(22),
              child: _svgIcon(
                'person_filled',
                size: 80,
                color: AppColors.mediumGreen,
              ),
            ),
          ),
        ),

        // EDIT PHOTO BUTTON
        Positioned(
          right: -12,
          bottom: 0,
          child: GestureDetector(
            onTap: () {
              ScaffoldMessenger.of(context).showSnackBar(
                const SnackBar(
                  content: Text(
                    'Fitur ubah foto profil akan diintegrasikan.',
                  ),
                ),
              );
            },
            child: Container(
              width: 45,
              height: 45,
              decoration: BoxDecoration(
                color: AppColors.mediumGreen,
                borderRadius: BorderRadius.circular(15),
              ),
              child: Center(
                child: _svgIcon(
                  'edit',
                  size: 23,
                  color: Colors.white,
                ),
              ),
            ),
          ),
        ),
      ],
    );
  }

  // USERNAME INPUT
  Widget _nameField() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.only(
            left: 3,
            bottom: 7,
          ),
          child: Text(
            'Nama Pengguna',
            style: TextStyle(
              fontSize: 15,
              fontWeight: FontWeight.w700,
              color: AppColors.darkGreen,
            ),
          ),
        ),

        TextField(
          controller: nameController,
          textInputAction: TextInputAction.done,
          style: const TextStyle(
            fontSize: 15,
            fontWeight: FontWeight.w600,
            color: AppColors.mediumGreen,
          ),
          decoration: InputDecoration(
            hintText: 'Masukkan nama pengguna',
            hintStyle: const TextStyle(
              color: AppColors.grey,
            ),

            prefixIcon: Padding(
              padding: const EdgeInsets.all(15),
              child: _svgIcon(
                'pencil',
                size: 23,
              ),
            ),

            filled: true,
            fillColor: AppColors.fieldBackground,

            contentPadding: const EdgeInsets.symmetric(
              horizontal: 18,
              vertical: 15,
            ),

            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: BorderSide.none,
            ),

            enabledBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: BorderSide.none,
            ),

            focusedBorder: OutlineInputBorder(
              borderRadius: BorderRadius.circular(20),
              borderSide: const BorderSide(
                color: AppColors.mediumGreen,
                width: 1.5,
              ),
            ),
          ),
        ),
      ],
    );
  }

  // SAVE BUTTON
  Widget _saveButton() {
    return SizedBox(
      width: double.infinity,
      height: 60,
      child: ElevatedButton(
        onPressed: () {
          final name = nameController.text.trim();

          if (name.isEmpty) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text(
                  'Nama pengguna tidak boleh kosong.',
                ),
              ),
            );
            return;
          }

          Navigator.pop(context, name);
        },
        style: ElevatedButton.styleFrom(
          backgroundColor: AppColors.mediumGreen,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
          ),
        ),
        child: const Text(
          'Simpan Perubahan',
          style: TextStyle(
            color: Colors.white,
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }

  // CANCEL BUTTON
  Widget _cancelButton() {
    return SizedBox(
      width: double.infinity,
      height: 60,
      child: ElevatedButton(
        onPressed: () {
          Navigator.pop(context);
        },
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFFE5D9D9),
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(20),
          ),
        ),
        child: const Text(
          'Batalkan Perubahan',
          style: TextStyle(
            color: AppColors.red,
            fontSize: 15,
            fontWeight: FontWeight.w700,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,

      body: SafeArea(
        top: false,
        bottom: false,
        child: Column(
          children: [
            // HEADER
            Container(
              height: 135,
              width: double.infinity,
              decoration: const BoxDecoration(
                color: AppColors.mediumGreen,
                borderRadius: BorderRadius.only(
                  bottomLeft: Radius.circular(30),
                  bottomRight: Radius.circular(30),
                ),
              ),
              padding: EdgeInsets.only(
                top: MediaQuery.of(context).padding.top,
              ),
              child: Stack(
                children: [
                  // BACK BUTTON
                  Positioned(
                    left: 22,
                    top: 22,
                    child: GestureDetector(
                      onTap: () => Navigator.pop(context),
                      child: const Icon(
                        Icons.arrow_back_ios_new,
                        color: Colors.white,
                        size: 23,
                      ),
                    ),
                  ),

                  // LOGO AND TITLE
                  Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        SvgPicture.asset(
                          'assets/images/logo_header.svg',
                          width: 27,
                          height: 27,
                          colorFilter: const ColorFilter.mode(
                            Colors.white,
                            BlendMode.srcIn,
                          ),
                        ),

                        const SizedBox(height: 5),

                        const Text(
                          'Edit Profil',
                          style: TextStyle(
                            fontSize: 23,
                            fontWeight: FontWeight.w700,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),

            // CONTENT AREA
            Expanded(
              child: Column(
                children: [
                  // CENTER CONTENT
                  Expanded(
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        return SingleChildScrollView(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 22,
                          ),
                          child: ConstrainedBox(
                            constraints: BoxConstraints(
                              minHeight: constraints.maxHeight,
                            ),
                            child: IntrinsicHeight(
                              child: Column(
                                mainAxisAlignment: MainAxisAlignment.center,
                                children: [
                                  _profilePicture(),

                                  const SizedBox(height: 65),

                                  _nameField(),
                                ],
                              ),
                            ),
                          ),
                        );
                      },
                    ),
                  ),

                  // BOTTOM BUTTONS
                  Padding(
                    padding: const EdgeInsets.fromLTRB(
                      19,
                      12,
                      19,
                      24,
                    ),
                    child: Column(
                      children: [
                        _saveButton(),

                        const SizedBox(height: 14),

                        _cancelButton(),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),

      // BOTTOM NAVIGATION
      bottomNavigationBar: BottomNavBar(
        currentIndex: 4,
        onTap: (_) {
          // Tidak berpindah halaman ketika sedang edit profil.
        },
      ),
    );
  }
}
