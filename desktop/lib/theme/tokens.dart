import 'package:flutter/material.dart';

/// SteadyDev Theme Tokens implementing the green brand identity with verified WCAG AA contrast.
@immutable
class SteadyDevThemeTokens extends ThemeExtension<SteadyDevThemeTokens> {
  final Color canvas;
  final Color panel;
  final Color subtleSurface;
  final Color primaryText;
  final Color secondaryText;
  final Color brandAction;
  final Color brandActionInk;
  final Color softBrandSurface;
  final Color dividerLine;
  final Color inputBoundary;
  final Color brandOutline;

  // Semantic status badge tokens
  final Color badgeConfirmedText;
  final Color badgeConfirmedBg;
  final Color badgeUnverifiedText;
  final Color badgeUnverifiedBg;
  final Color badgeJudgmentText;
  final Color badgeJudgmentBg;

  const SteadyDevThemeTokens({
    required this.canvas,
    required this.panel,
    required this.subtleSurface,
    required this.primaryText,
    required this.secondaryText,
    required this.brandAction,
    required this.brandActionInk,
    required this.softBrandSurface,
    required this.dividerLine,
    required this.inputBoundary,
    required this.brandOutline,
    required this.badgeConfirmedText,
    required this.badgeConfirmedBg,
    required this.badgeUnverifiedText,
    required this.badgeUnverifiedBg,
    required this.badgeJudgmentText,
    required this.badgeJudgmentBg,
  });

  /// Light theme tokens (Forest Green action, 6.53:1 contrast on white)
  static const light = SteadyDevThemeTokens(
    canvas: Color(0xFFF5F8F4),
    panel: Color(0xFFFFFFFF),
    subtleSurface: Color(0xFFEDF3EC),
    primaryText: Color(0xFF172A1C),
    secondaryText: Color(0xFF536457),
    brandAction: Color(0xFF146C2E),
    brandActionInk: Color(0xFFFFFFFF),
    softBrandSurface: Color(0xFFEAF5E9),
    dividerLine: Color(0xFFD7E2D7),
    inputBoundary: Color(0xFF718874),
    brandOutline: Color(0xFF8AAF90),
    badgeConfirmedText: Color(0xFF226542),
    badgeConfirmedBg: Color(0xFFEDF6F0),
    badgeUnverifiedText: Color(0xFF8C5818),
    badgeUnverifiedBg: Color(0xFFFFF6E8),
    badgeJudgmentText: Color(0xFF7251A2),
    badgeJudgmentBg: Color(0xFFF3EFFA),
  );

  /// Dark theme tokens (Neon green action with deep dark green ink, 13.30:1 contrast)
  static const dark = SteadyDevThemeTokens(
    canvas: Color(0xFF001A06),
    panel: Color(0xFF092410),
    subtleSurface: Color(0xFF12311A),
    primaryText: Color(0xFFEAFFEA),
    secondaryText: Color(0xFFA8C2AC),
    brandAction: Color(0xFF00FF00),
    brandActionInk: Color(0xFF001A06),
    softBrandSurface: Color(0xFF123A1C),
    dividerLine: Color(0xFF35563C),
    inputBoundary: Color(0xFF749B7D),
    brandOutline: Color(0xFF568A61),
    badgeConfirmedText: Color(0xFF92D3B0),
    badgeConfirmedBg: Color(0xFF19372A),
    badgeUnverifiedText: Color(0xFFF0C38A),
    badgeUnverifiedBg: Color(0xFF3D3224),
    badgeJudgmentText: Color(0xFFD2B5F2),
    badgeJudgmentBg: Color(0xFF342A43),
  );

  @override
  SteadyDevThemeTokens copyWith({
    Color? canvas,
    Color? panel,
    Color? subtleSurface,
    Color? primaryText,
    Color? secondaryText,
    Color? brandAction,
    Color? brandActionInk,
    Color? softBrandSurface,
    Color? dividerLine,
    Color? inputBoundary,
    Color? brandOutline,
    Color? badgeConfirmedText,
    Color? badgeConfirmedBg,
    Color? badgeUnverifiedText,
    Color? badgeUnverifiedBg,
    Color? badgeJudgmentText,
    Color? badgeJudgmentBg,
  }) {
    return SteadyDevThemeTokens(
      canvas: canvas ?? this.canvas,
      panel: panel ?? this.panel,
      subtleSurface: subtleSurface ?? this.subtleSurface,
      primaryText: primaryText ?? this.primaryText,
      secondaryText: secondaryText ?? this.secondaryText,
      brandAction: brandAction ?? this.brandAction,
      brandActionInk: brandActionInk ?? this.brandActionInk,
      softBrandSurface: softBrandSurface ?? this.softBrandSurface,
      dividerLine: dividerLine ?? this.dividerLine,
      inputBoundary: inputBoundary ?? this.inputBoundary,
      brandOutline: brandOutline ?? this.brandOutline,
      badgeConfirmedText: badgeConfirmedText ?? this.badgeConfirmedText,
      badgeConfirmedBg: badgeConfirmedBg ?? this.badgeConfirmedBg,
      badgeUnverifiedText: badgeUnverifiedText ?? this.badgeUnverifiedText,
      badgeUnverifiedBg: badgeUnverifiedBg ?? this.badgeUnverifiedBg,
      badgeJudgmentText: badgeJudgmentText ?? this.badgeJudgmentText,
      badgeJudgmentBg: badgeJudgmentBg ?? this.badgeJudgmentBg,
    );
  }

  @override
  SteadyDevThemeTokens lerp(ThemeExtension<SteadyDevThemeTokens>? other, double t) {
    if (other is! SteadyDevThemeTokens) return this;
    return SteadyDevThemeTokens(
      canvas: Color.lerp(canvas, other.canvas, t)!,
      panel: Color.lerp(panel, other.panel, t)!,
      subtleSurface: Color.lerp(subtleSurface, other.subtleSurface, t)!,
      primaryText: Color.lerp(primaryText, other.primaryText, t)!,
      secondaryText: Color.lerp(secondaryText, other.secondaryText, t)!,
      brandAction: Color.lerp(brandAction, other.brandAction, t)!,
      brandActionInk: Color.lerp(brandActionInk, other.brandActionInk, t)!,
      softBrandSurface: Color.lerp(softBrandSurface, other.softBrandSurface, t)!,
      dividerLine: Color.lerp(dividerLine, other.dividerLine, t)!,
      inputBoundary: Color.lerp(inputBoundary, other.inputBoundary, t)!,
      brandOutline: Color.lerp(brandOutline, other.brandOutline, t)!,
      badgeConfirmedText: Color.lerp(badgeConfirmedText, other.badgeConfirmedText, t)!,
      badgeConfirmedBg: Color.lerp(badgeConfirmedBg, other.badgeConfirmedBg, t)!,
      badgeUnverifiedText: Color.lerp(badgeUnverifiedText, other.badgeUnverifiedText, t)!,
      badgeUnverifiedBg: Color.lerp(badgeUnverifiedBg, other.badgeUnverifiedBg, t)!,
      badgeJudgmentText: Color.lerp(badgeJudgmentText, other.badgeJudgmentText, t)!,
      badgeJudgmentBg: Color.lerp(badgeJudgmentBg, other.badgeJudgmentBg, t)!,
    );
  }
}
