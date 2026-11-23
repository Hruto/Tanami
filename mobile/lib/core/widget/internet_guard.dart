
import 'dart:async';

import 'package:flutter/material.dart';
import 'package:internet_connection_checker_plus/internet_connection_checker_plus.dart';

import 'no_internet_page.dart';


class InternetGuard extends StatefulWidget {
  final Widget child;

  const InternetGuard({
    super.key,
    required this.child,
  });

  @override
  State<InternetGuard> createState() => _InternetGuardState();
}

class _InternetGuardState extends State<InternetGuard> {
  bool _isConnected = true;
  late final StreamSubscription<InternetStatus> _subscription;

  @override
  void initState() {
    super.initState();

    _checkConnection();

    _subscription = InternetConnection().onStatusChange.listen(
      (status) {
        if (!mounted) return;

        setState(() {
          _isConnected = status == InternetStatus.connected;
        });
      },
    );
  }

  Future<void> _checkConnection() async {
    final result = await InternetConnection().hasInternetAccess;

    if (!mounted) return;

    setState(() {
      _isConnected = result;
    });
  }

  @override
  void dispose() {
    _subscription.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    if (!_isConnected) {
      return NoInternetPage(
        onRetry: _checkConnection,
      );
    }

    return widget.child;
  }
}
