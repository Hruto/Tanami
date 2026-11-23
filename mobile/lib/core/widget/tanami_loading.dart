
import 'dart:math' as math;
import 'package:flutter/material.dart';

class TanamiLoading extends StatefulWidget {
  const TanamiLoading({super.key});

  @override
  State<TanamiLoading> createState() => _TanamiLoadingState();
}

class _TanamiLoadingState extends State<TanamiLoading>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();

    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 900),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: List.generate(3, (index) {
        return AnimatedBuilder(
          animation: _controller,
          builder: (context, child) {
            final progress =
                (_controller.value * 2 * math.pi) -
                (index * 2 * math.pi / 3);

            final scale = 0.6 + (0.4 * 
                ((math.sin(progress) + 1) / 2));

            return Padding(
              padding: const EdgeInsets.symmetric(horizontal: 4),
              child: Transform.scale(
                scale: scale,
                child: Container(
                  width: 9,
                  height: 9,
                  decoration: const BoxDecoration(
                    color: Color(0xFF2E6B52),
                    shape: BoxShape.circle,
                  ),
                ),
              ),
            );
          },
        );
      }),
    );
  }
}
