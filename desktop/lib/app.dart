import 'package:flutter/material.dart';

import 'services/api_client.dart';
import 'theme/theme_manager.dart';
import 'widgets/steady_dev_scaffold.dart';

export 'widgets/steady_dev_scaffold.dart';

class SteadyDevApp extends StatelessWidget {
  final ThemeManager themeManager;
  final SteadyDevApiClient? initialApiClient;

  const SteadyDevApp({
    super.key,
    required this.themeManager,
    this.initialApiClient,
  });

  @override
  Widget build(BuildContext context) {
    return ListenableBuilder(
      listenable: themeManager,
      builder: (context, _) {
        return MaterialApp(
          title: 'SteadyDev',
          debugShowCheckedModeBanner: false,
          theme: ThemeManager.lightTheme,
          darkTheme: ThemeManager.darkTheme,
          themeMode: themeManager.themeMode,
          home: SteadyDevScaffold(
            themeManager: themeManager,
            apiClient: initialApiClient,
          ),
        );
      },
    );
  }
}
