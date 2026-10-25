import 'package:flutter/material.dart';

import 'app.dart';
import 'services/process_manager.dart';
import 'theme/theme_manager.dart';

export 'app.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final themeManager = ThemeManager();
  await themeManager.loadPreference();

  final processManager = BackendProcessManager();

  runApp(SteadyDevApp(
    themeManager: themeManager,
    processManager: processManager,
    autoStartBackend: true,
  ));
}
