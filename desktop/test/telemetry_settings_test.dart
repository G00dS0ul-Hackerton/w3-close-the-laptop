import 'package:desktop/models/session_models.dart';
import 'package:desktop/services/api_client.dart';
import 'package:desktop/theme/tokens.dart';
import 'package:desktop/views/diagnostics_dialog.dart';
import 'package:desktop/views/telemetry_settings_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

class MockSteadyDevApiClient extends SteadyDevApiClient {
  TelemetryConfigData? mockConfig;
  bool updateCalled = false;
  bool lastEnabledArg = false;
  String? lastDsnArg;

  MockSteadyDevApiClient({
    super.baseUrl = 'http://127.0.0.1:9999',
    super.token = 'test-token',
    this.mockConfig,
  });

  @override
  Future<TelemetryConfigData?> getTelemetryConfig() async {
    return mockConfig;
  }

  @override
  Future<TelemetryConfigData?> updateTelemetryConfig({
    required bool enabled,
    String? dsn,
  }) async {
    updateCalled = true;
    lastEnabledArg = enabled;
    lastDsnArg = dsn;
    mockConfig = TelemetryConfigData(
      enabled: enabled,
      dsnConfigured: dsn != null || (mockConfig?.dsnConfigured ?? false),
      maskedDsn: dsn != null ? 'https://mask***@sentry.io/1' : (mockConfig?.maskedDsn ?? ''),
      exportState: enabled ? 'local_only' : 'disabled',
      verifiedDelivery: false,
    );
    return mockConfig;
  }

  @override
  Future<ReviewDiagnosticsData?> getReviewDiagnostics() async {
    return ReviewDiagnosticsData(
      reviewId: 'test-review',
      phase: 'completed',
      isReviewing: false,
      repoName: 'test-repo',
      totalFiles: 1,
      totalChunks: 1,
      currentChunk: 1,
      currentFiles: ['test.py'],
      chunkDiagnostics: [],
      elapsedMs: 1200.0,
      deadlineSeconds: 180.0,
      deadlineExceeded: false,
      status: 'clean',
      createdAt: '2026-10-23T18:00:00Z',
      updatedAt: '2026-10-23T18:00:01Z',
    );
  }
}

void main() {
  Widget buildSettingsApp(MockSteadyDevApiClient client, {TelemetryConfigData? initialConfig}) {
    return MaterialApp(
      theme: ThemeData.light().copyWith(
        extensions: [SteadyDevThemeTokens.light],
      ),
      home: Scaffold(
        body: TelemetrySettingsDialog(
          apiClient: client,
          initialConfig: initialConfig,
        ),
      ),
    );
  }

  Widget buildDiagnosticsApp(MockSteadyDevApiClient client) {
    return MaterialApp(
      theme: ThemeData.light().copyWith(
        extensions: [SteadyDevThemeTokens.light],
      ),
      home: Scaffold(
        body: DiagnosticsDialog(
          apiClient: client,
        ),
      ),
    );
  }

  testWidgets('TelemetrySettingsDialog renders toggle, DSN field, and privacy disclosures', (
    tester,
  ) async {
    final client = MockSteadyDevApiClient(
      mockConfig: TelemetryConfigData(
        enabled: false,
        dsnConfigured: false,
        maskedDsn: '',
        exportState: 'disabled',
        verifiedDelivery: false,
      ),
    );

    await tester.pumpWidget(buildSettingsApp(client));
    await tester.pumpAndSettle();

    expect(find.text('Sentry Telemetry Settings'), findsOneWidget);
    expect(find.text('Enable Sentry Tracing Export'), findsOneWidget);
    expect(find.text('Data Privacy & Dispatch Disclosures'), findsOneWidget);
    expect(find.textContaining('Strict Sanitization'), findsOneWidget);
    expect(find.textContaining('Irreversible Dispatch'), findsOneWidget);
    expect(find.textContaining('Offline Core'), findsOneWidget);
    expect(find.text('DISABLED'), findsOneWidget);
  });

  testWidgets('TelemetrySettingsDialog displays verified delivery status and trace URL when delivered', (
    tester,
  ) async {
    final client = MockSteadyDevApiClient(
      mockConfig: TelemetryConfigData(
        enabled: true,
        dsnConfigured: true,
        maskedDsn: 'https://key1***@o1234.ingest.sentry.io/999',
        exportState: 'verified_delivered',
        lastTraceId: 'cae934c2f4774308823593cde2c5db02',
        traceUrl: 'https://o1234.sentry.io/explore/traces/trace/cae934c2f4774308823593cde2c5db02/',
        verifiedDelivery: true,
      ),
    );

    await tester.pumpWidget(buildSettingsApp(client));
    await tester.pumpAndSettle();

    expect(find.text('VERIFIED_DELIVERED'), findsOneWidget);
    expect(
        find.text('Last Trace ID: cae934c2f4774308823593cde2c5db02'), findsOneWidget);
    expect(
      find.byWidgetPredicate((w) =>
          w is SelectableText &&
          (w.data?.contains('https://o1234.sentry.io') ?? false)),
      findsOneWidget,
    );
  });

  testWidgets('DiagnosticsDialog shows Sentry Telemetry Export card with verified delivery', (
    tester,
  ) async {
    final client = MockSteadyDevApiClient(
      mockConfig: TelemetryConfigData(
        enabled: true,
        dsnConfigured: true,
        maskedDsn: 'https://key1***@o1234.ingest.sentry.io/999',
        exportState: 'verified_delivered',
        lastTraceId: 'cae934c2f4774308823593cde2c5db02',
        traceUrl: 'https://o1234.sentry.io/explore/traces/trace/cae934c2f4774308823593cde2c5db02/',
        verifiedDelivery: true,
      ),
    );

    await tester.pumpWidget(buildDiagnosticsApp(client));
    await tester.pumpAndSettle();

    expect(find.text('Sentry Telemetry:'), findsOneWidget);
    expect(find.text('VERIFIED DELIVERED'), findsOneWidget);
    expect(find.text('Trace ID: cae934c2f4774308823593cde2c5db02'), findsOneWidget);
    expect(find.text('Configure'), findsOneWidget);
  });
}
