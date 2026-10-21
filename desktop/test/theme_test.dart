import 'dart:math';

import 'package:desktop/theme/theme_manager.dart';
import 'package:desktop/theme/tokens.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

double _luminance(Color c) {
  double channel(double v) {
    return v <= 0.03928 ? v / 12.92 : pow((v + 0.055) / 1.055, 2.4).toDouble();
  }

  final r = channel(c.r);
  final g = channel(c.g);
  final b = channel(c.b);
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

double _contrastRatio(Color c1, Color c2) {
  final l1 = _luminance(c1);
  final l2 = _luminance(c2);
  final bright = max(l1, l2);
  final dark = min(l1, l2);
  return (bright + 0.05) / (dark + 0.05);
}

void main() {
  group('SteadyDevThemeTokens Contrast Tests', () {
    test('Light theme tokens meet WCAG AA requirements', () {
      const tokens = SteadyDevThemeTokens.light;

      // Primary text on white panel >= 4.5:1
      final textOnPanel = _contrastRatio(tokens.primaryText, tokens.panel);
      expect(textOnPanel, greaterThanOrEqualTo(4.5));

      // Brand action on white panel >= 4.5:1
      final actionOnPanel = _contrastRatio(tokens.brandAction, tokens.panel);
      expect(actionOnPanel, greaterThanOrEqualTo(4.5));

      // Primary button text on brand action >= 4.5:1
      final buttonTextOnAction = _contrastRatio(tokens.brandActionInk, tokens.brandAction);
      expect(buttonTextOnAction, greaterThanOrEqualTo(4.5));
    });

    test('Dark theme tokens meet WCAG AA requirements', () {
      const tokens = SteadyDevThemeTokens.dark;

      // Primary text on dark panel >= 4.5:1
      final textOnPanel = _contrastRatio(tokens.primaryText, tokens.panel);
      expect(textOnPanel, greaterThanOrEqualTo(4.5));

      // Brand neon action on dark canvas >= 4.5:1
      final actionOnCanvas = _contrastRatio(tokens.brandAction, tokens.canvas);
      expect(actionOnCanvas, greaterThanOrEqualTo(4.5));

      // Deep green ink on neon action button >= 4.5:1 (actually > 13:1)
      final inkOnNeon = _contrastRatio(tokens.brandActionInk, tokens.brandAction);
      expect(inkOnNeon, greaterThanOrEqualTo(4.5));
    });
  });

  group('ThemeManager Persistence & Fallback', () {
    test('ThemeManager defaults to ThemeMode.system', () {
      final manager = ThemeManager();
      expect(manager.themeMode, equals(ThemeMode.system));
    });

    test('ThemeManager updates mode and notifies listeners', () async {
      final manager = ThemeManager();
      bool notified = false;
      manager.addListener(() {
        notified = true;
      });

      await manager.setThemeMode(ThemeMode.dark);
      expect(manager.themeMode, equals(ThemeMode.dark));
      expect(notified, isTrue);
    });
  });
}
