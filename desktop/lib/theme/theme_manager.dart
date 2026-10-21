import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';

import 'tokens.dart';

/// Manages application appearance mode (System, Light, Dark) and local persistence.
class ThemeManager extends ChangeNotifier {
  final bool persistToDisk;
  ThemeMode _themeMode = ThemeMode.system;

  ThemeManager({this.persistToDisk = true});

  ThemeMode get themeMode => _themeMode;

  static const String _fileName = 'preferences.json';

  static Directory get _appDataDir {
    final localAppData = Platform.environment['LOCALAPPDATA'] ??
        Platform.environment['APPDATA'] ??
        Directory.systemTemp.path;
    return Directory('$localAppData\\SteadyDev');
  }

  /// Initialize and load saved appearance preference from local JSON file.
  Future<void> loadPreference() async {
    if (!persistToDisk) {
      notifyListeners();
      return;
    }
    try {
      final file = File('${_appDataDir.path}\\$_fileName');
      if (!await file.exists()) {
        _themeMode = ThemeMode.system;
        notifyListeners();
        return;
      }
      final raw = await file.readAsString();
      final map = jsonDecode(raw) as Map<String, dynamic>;
      final val = map['themeMode'] as String?;
      switch (val) {
        case 'light':
          _themeMode = ThemeMode.light;
          break;
        case 'dark':
          _themeMode = ThemeMode.dark;
          break;
        default:
          _themeMode = ThemeMode.system;
          break;
      }
    } catch (_) {
      // Safe fallback per w3-ui-spec.md:71: Corrupted or missing values must NEVER crash startup
      _themeMode = ThemeMode.system;
    }
    notifyListeners();
  }

  /// Update appearance preference and persist to disk.
  Future<void> setThemeMode(ThemeMode mode) async {
    if (_themeMode == mode) return;
    _themeMode = mode;
    notifyListeners();

    if (!persistToDisk) return;

    try {
      final dir = _appDataDir;
      if (!await dir.exists()) {
        await dir.create(recursive: true);
      }
      final file = File('${dir.path}\\$_fileName');
      final val = mode == ThemeMode.light
          ? 'light'
          : mode == ThemeMode.dark
              ? 'dark'
              : 'system';
      await file.writeAsString(jsonEncode({'themeMode': val}));
    } catch (_) {
      // Non-fatal logging for preference write failure
    }
  }

  /// Construct Light ThemeData with brand tokens
  static ThemeData get lightTheme {
    const tokens = SteadyDevThemeTokens.light;
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.light,
      scaffoldBackgroundColor: tokens.canvas,
      colorScheme: ColorScheme.light(
        surface: tokens.panel,
        onSurface: tokens.primaryText,
        primary: tokens.brandAction,
        onPrimary: tokens.brandActionInk,
        surfaceContainerHighest: tokens.subtleSurface,
        outline: tokens.inputBoundary,
      ),
      extensions: const [tokens],
    );
  }

  /// Construct Dark ThemeData with brand tokens
  static ThemeData get darkTheme {
    const tokens = SteadyDevThemeTokens.dark;
    return ThemeData(
      useMaterial3: true,
      brightness: Brightness.dark,
      scaffoldBackgroundColor: tokens.canvas,
      colorScheme: ColorScheme.dark(
        surface: tokens.panel,
        onSurface: tokens.primaryText,
        primary: tokens.brandAction,
        onPrimary: tokens.brandActionInk,
        surfaceContainerHighest: tokens.subtleSurface,
        outline: tokens.inputBoundary,
      ),
      extensions: const [tokens],
    );
  }
}
