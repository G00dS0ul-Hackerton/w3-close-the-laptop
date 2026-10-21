import 'package:flutter/material.dart';

import 'app.dart';
import 'services/api_client.dart';
import 'theme/theme_manager.dart';

export 'app.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final themeManager = ThemeManager();
  await themeManager.loadPreference();

  final client = SteadyDevApiClient(
    baseUrl: 'http://127.0.0.1:8765',
    token: 'dev-token-123',
  );

  runApp(SteadyDevApp(
    themeManager: themeManager,
    initialApiClient: client,
  ));
}
