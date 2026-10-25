import 'package:flutter/material.dart';

import 'services/api_client.dart';
import 'services/process_manager.dart';
import 'theme/theme_manager.dart';
import 'theme/tokens.dart';
import 'widgets/startup_error_view.dart';
import 'widgets/steady_dev_scaffold.dart';

export 'widgets/startup_error_view.dart';
export 'widgets/steady_dev_scaffold.dart';

class SteadyDevApp extends StatefulWidget {
  final ThemeManager themeManager;
  final SteadyDevApiClient? initialApiClient;
  final BackendProcessManager? processManager;
  final bool autoStartBackend;

  const SteadyDevApp({
    super.key,
    required this.themeManager,
    this.initialApiClient,
    this.processManager,
    this.autoStartBackend = false,
  });

  @override
  State<SteadyDevApp> createState() => _SteadyDevAppState();
}

class _SteadyDevAppState extends State<SteadyDevApp> with WidgetsBindingObserver {
  late final BackendProcessManager _processManager;
  SteadyDevApiClient? _apiClient;
  bool _isStarting = false;
  StartupFailureException? _startupError;
  bool _offlineFallback = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _processManager = widget.processManager ?? BackendProcessManager();
    _apiClient = widget.initialApiClient;

    if (widget.autoStartBackend && _apiClient == null) {
      _startBackend();
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    if (widget.autoStartBackend) {
      _processManager.stopBackend();
    }
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.detached) {
      if (widget.autoStartBackend) {
        _processManager.stopBackend();
      }
    }
  }

  Future<void> _startBackend() async {
    setState(() {
      _isStarting = true;
      _startupError = null;
      _offlineFallback = false;
    });

    try {
      // 1. Probe if backend is already running on 8765
      final existingClient = await BackendProcessManager.probeExistingBackend();
      if (existingClient != null) {
        if (!mounted) return;
        setState(() {
          _apiClient = existingClient;
          _isStarting = false;
        });
        return;
      }

      // 2. Otherwise start backend process silently
      final client = await _processManager.startBackend();
      if (!mounted) return;
      setState(() {
        _apiClient = client;
        _isStarting = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _isStarting = false;
        if (e is StartupFailureException) {
          _startupError = e;
        } else {
          _startupError = StartupFailureException(
            message: e.toString(),
            recentStderr: [e.toString()],
          );
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: widget.themeManager,
      builder: (context, _) {
        final isDark = widget.themeManager.themeMode == ThemeMode.dark;
        final tokens = isDark ? SteadyDevThemeTokens.dark : SteadyDevThemeTokens.light;

        Widget home;
        if (_isStarting) {
          home = Scaffold(
            backgroundColor: tokens.canvas,
            body: Center(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Semantics(
                    label: 'SteadyDev',
                    image: true,
                    child: SizedBox(
                      height: 32,
                      child: AspectRatio(
                        aspectRatio: 1200 / 240,
                        child: Image.asset(
                          isDark
                              ? 'assets/brand/steadydev-horizontal-dark.png'
                              : 'assets/brand/steadydev-horizontal-light.png',
                          fit: BoxFit.contain,
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 24),
                  CircularProgressIndicator(
                    valueColor: AlwaysStoppedAnimation<Color>(tokens.brandAction),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'Starting SteadyDev local engine...',
                    style: TextStyle(
                      fontSize: 14,
                      color: tokens.secondaryText,
                    ),
                  ),
                ],
              ),
            ),
          );
        } else if (_startupError != null && !_offlineFallback) {
          home = Scaffold(
            backgroundColor: tokens.canvas,
            body: StartupErrorView(
              errorMessage: _startupError!.message,
              logPath: _startupError!.logPath,
              recentStderr: _startupError!.recentStderr,
              onRetry: _startBackend,
              onDismissOffline: () {
                setState(() {
                  _offlineFallback = true;
                });
              },
            ),
          );
        } else {
          home = SteadyDevScaffold(
            themeManager: widget.themeManager,
            apiClient: _apiClient,
          );
        }

        return MaterialApp(
          title: 'SteadyDev',
          debugShowCheckedModeBanner: false,
          theme: ThemeManager.lightTheme,
          darkTheme: ThemeManager.darkTheme,
          themeMode: widget.themeManager.themeMode,
          home: home,
        );
      },
    );
  }
}
