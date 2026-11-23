

import 'package:flutter/material.dart';

import 'package:flutter_svg/flutter_svg.dart';



import '../../../core/constant/app_colors.dart';

import 'edit_profile_page.dart';



class ProfilePage extends StatefulWidget {

  const ProfilePage({super.key});



  @override

  State<ProfilePage> createState() => _ProfilePageState();

}



class _ProfilePageState extends State<ProfilePage> {

  String userName = 'Anonim';

  String fullName = 'Anonim Gunardi';

  final String email = 'Anonim@gmail.com';



  bool notificationEnabled = true;



  // SVG ICON

  Widget _svgIcon(

    String name, {

    double size = 25,

    Color color = AppColors.darkGreen,

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

      placeholderBuilder: (context) {

        return SizedBox(

          width: size,

          height: size,

          child: Icon(

            Icons.image_not_supported_outlined,

            size: size * 0.8,

            color: color,

          ),

        );

      },

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



        // EDIT PROFILE PHOTO

        Positioned(

          right: -9,

          bottom: 3,

          child: GestureDetector(

            onTap: _openEditProfile,

            child: Container(

              width: 44,

              height: 44,

              decoration: BoxDecoration(

                color: AppColors.mediumGreen,

                borderRadius: BorderRadius.circular(15),

              ),

              child: Center(

                child: _svgIcon(

                  'edit',

                  size: 23,

                  color: AppColors.background,

                ),

              ),

            ),

          ),

        ),

      ],

    );

  }



  // NAVIGATE TO EDIT PROFILE

  Future<void> _openEditProfile() async {

    final result = await Navigator.push<String>(

      context,

      MaterialPageRoute(

        builder: (_) => EditProfilePage(

          initialName: userName,

        ),

      ),

    );



    if (!mounted) return;



    if (result != null && result.trim().isNotEmpty) {

      setState(() {

        userName = result.trim();

        fullName = result.trim();

      });

    }

  }



  // SECTION TITLE

  Widget _sectionTitle(String title) {

    return Padding(

      padding: const EdgeInsets.only(

        left: 2,

        bottom: 12,

      ),

      child: Text(

        title,

        style: const TextStyle(

          fontSize: 15,

          fontWeight: FontWeight.w700,

          color: Colors.black,

        ),

      ),

    );

  }



  // ACCOUNT INFORMATION CARD

  Widget _accountCard() {

    return Container(

      width: double.infinity,

      padding: const EdgeInsets.symmetric(

        horizontal: 16,

        vertical: 13,

      ),

      decoration: BoxDecoration(

        color: AppColors.background,

        borderRadius: BorderRadius.circular(20),

        boxShadow: [

          BoxShadow(

            color: Colors.black.withValues(alpha: 0.13),

            blurRadius: 8,

            offset: const Offset(0, 4),

          ),

        ],

      ),

      child: Column(

        children: [

          // USERNAME

          Row(

            children: [

              _svgIcon('person', size: 25),



              const SizedBox(width: 16),



              Expanded(

                child: Text(

                  fullName,

                  style: const TextStyle(

                    fontSize: 12,

                    fontWeight: FontWeight.w700,

                    color: AppColors.darkGreen,

                  ),

                ),

              ),



              GestureDetector(

                onTap: _openEditProfile,

                child: _svgIcon(

                  'edit',

                  size: 23,

                ),

              ),

            ],

          ),



          const SizedBox(height: 26),



          // EMAIL

          Row(

            children: [

              _svgIcon('email', size: 25),



              const SizedBox(width: 16),



              Expanded(

                child: Text(

                  email,

                  style: const TextStyle(

                    fontSize: 12,

                    fontWeight: FontWeight.w600,

                    color: AppColors.grey,

                  ),

                ),

              ),

            ],

          ),

        ],

      ),

    );

  }



  // ACCOUNT SETTINGS CARD

  Widget _settingsCard() {

    return Container(

      width: double.infinity,

      padding: const EdgeInsets.symmetric(

        horizontal: 16,

        vertical: 11,

      ),

      decoration: BoxDecoration(

        color: AppColors.background,

        borderRadius: BorderRadius.circular(20),

        boxShadow: [

          BoxShadow(

            color: Colors.black.withValues(alpha: 0.13),

            blurRadius: 8,

            offset: const Offset(0, 4),

          ),

        ],

      ),

      child: Column(

        children: [

          // CHANGE PASSWORD

          InkWell(

            onTap: () {

              ScaffoldMessenger.of(context).showSnackBar(

                const SnackBar(

                  content: Text(

                    'Fitur ganti password akan diintegrasikan.',

                  ),

                ),

              );

            },

            child: Row(

              children: [

                _svgIcon('lock', size: 25),



                const SizedBox(width: 16),



                const Expanded(

                  child: Text(

                    'Ganti Password',

                    style: TextStyle(

                      fontSize: 12,

                      fontWeight: FontWeight.w700,

                      color: AppColors.darkGreen,

                    ),

                  ),

                ),



                const Icon(

                  Icons.chevron_right,

                  size: 30,

                  color: AppColors.darkGreen,

                ),

              ],

            ),

          ),



          const SizedBox(height: 17),



          // NOTIFICATION SETTINGS

          Row(

            children: [

              _svgIcon('notification', size: 25),



              const SizedBox(width: 16),



              const Expanded(

                child: Text(

                  'Pengaturan Notifikasi',

                  style: TextStyle(

                    fontSize: 12,

                    fontWeight: FontWeight.w700,

                    color: AppColors.darkGreen,

                  ),

                ),

              ),



              Transform.scale(

                scale: 0.9,

                child: Switch(

                  value: notificationEnabled,

                  onChanged: (value) {

                    setState(() {

                      notificationEnabled = value;

                    });

                  },

                  activeThumbColor: Colors.white,

                  activeTrackColor: AppColors.mediumGreen,

                  inactiveThumbColor: Colors.white,

                  inactiveTrackColor: AppColors.grey,

                ),

              ),

            ],

          ),

        ],

      ),

    );

  }



  // LOGOUT BUTTON

  Widget _logoutButton() {

    return SizedBox(

      width: double.infinity,

      height: 60,

      child: ElevatedButton(

        onPressed: _showLogoutDialog,

        style: ElevatedButton.styleFrom(

          backgroundColor: const Color(0xFFE5D9D9),

          foregroundColor: AppColors.red,

          elevation: 4,

          shadowColor: Colors.black26,

          shape: RoundedRectangleBorder(

            borderRadius: BorderRadius.circular(20),

          ),

        ),

        child: Row(

          mainAxisAlignment: MainAxisAlignment.center,

          children: [

            _svgIcon(

              'logout',

              size: 23,

              color: AppColors.red,

            ),



            const SizedBox(width: 12),



            const Text(

              'Keluar Akun',

              style: TextStyle(

                color: AppColors.red,

                fontSize: 16,

                fontWeight: FontWeight.w700,

              ),

            ),

          ],

        ),

      ),

    );

  }



  // LOGOUT CONFIRMATION

  void _showLogoutDialog() {

    showDialog(

      context: context,

      builder: (dialogContext) {

        return AlertDialog(

          title: const Text('Keluar Akun'),

          content: const Text(

            'Apakah kamu yakin ingin keluar dari akun?',

          ),

          actions: [

            TextButton(

              onPressed: () {

                Navigator.pop(dialogContext);

              },

              child: const Text('Batal'),

            ),



            TextButton(

              onPressed: () {

                Navigator.pop(dialogContext);



                // TODO: Integrasikan logout API.

              },

              child: const Text(

                'Keluar',

                style: TextStyle(

                  color: AppColors.red,

                ),

              ),

            ),

          ],

        );

      },

    );

  }



  @override

  Widget build(BuildContext context) {

    return Scaffold(

      backgroundColor: AppColors.background,

      body: SafeArea(

        top: false,

        child: Column(

          children: [

            // TOP HEADER

            Container(

              height: 94,

              width: double.infinity,

              color: AppColors.mediumGreen,

              padding: EdgeInsets.only(

                top: MediaQuery.of(context).padding.top,

              ),

              child: Center(

                child: SvgPicture.asset(

                  'assets/images/logo_header.svg',

                  width: 27,

                  height: 27,

                  fit: BoxFit.contain,

                  colorFilter: const ColorFilter.mode(

                    Colors.white,

                    BlendMode.srcIn,

                  ),

                ),

              ),

            ),



            // PROFILE CONTENT

            Expanded(

              child: SingleChildScrollView(

                padding: const EdgeInsets.fromLTRB(

                  20,

                  24,

                  20,

                  20,

                ),

                child: Column(

                  children: [

                    _profilePicture(),



                    const SizedBox(height: 12),



                    Text(

                      userName,

                      style: const TextStyle(

                        fontSize: 23,

                        fontWeight: FontWeight.w700,

                        color: AppColors.darkGreen,

                      ),

                    ),



                    const SizedBox(height: 32),



                    // ACCOUNT INFORMATION

                    _sectionTitle('Informasi Akun'),

                    _accountCard(),



                    const SizedBox(height: 32),



                    // ACCOUNT SETTINGS

                    _sectionTitle('Pengaturan Akun'),

                    _settingsCard(),



                    const SizedBox(height: 32),



                    // LOGOUT

                    _logoutButton(),

                  ],

                ),

              ),

            ),

          ],

        ),

      ),

    );

  }

}
