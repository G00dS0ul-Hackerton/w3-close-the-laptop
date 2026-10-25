import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:http/http.dart' as http;
import 'package:http/testing.dart';
import 'package:desktop/models/session_models.dart';
import 'package:desktop/services/api_client.dart';
import 'package:desktop/views/diagnostics_dialog.dart';

class MockSteadyDevApiClient extends SteadyDevApiClient {
  TelemetryConfigData? mockConfig;

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
      elapsedMs: 800.0,
      deadlineSeconds: 180.0,
      deadlineExceeded: false,
      status: 'clean',
      createdAt: '2026-10-25T18:00:00Z',
      updatedAt: '2026-10-25T18:00:01Z',
    );
  }
}

void main() {
  group('Cross-Process Correlation & Latency Separation', () {
    test('requestReview attaches correlation headers and measures separate timings', () async {
      final mockClient = MockClient((request) async {
        // Assert loopback Bearer token preserved
        expect(request.headers['Authorization'], 'Bearer test-token');
        // Assert correlation headers attached
        expect(request.headers.containsKey('X-Run-ID'), isTrue);
        expect(request.headers.containsKey('sentry-trace'), isTrue);
        expect(request.headers.containsKey('baggage'), isTrue);

        return http.Response(
          '{"packet_id":"p1","status":"clean","findings":[],"retired_finding_ids":[],"closing_summary":"ok","restart_note":"","timing_ms":{"total_duration_ms":42.0}}',
          200,
        );
      });

      final apiClient = SteadyDevApiClient(
        baseUrl: 'http://127.0.0.1:8000',
        token: 'test-token',
        client: mockClient,
      );

      final res = await apiClient.requestReview(
        repoPath: 'C:\\test\\repo',
        intention: 'test',
        criteria: [],
        receipts: [],
        sentryTrace: '12345678901234567890123456789012-abcdef1234567890-1',
        baggage: 'sentry-env=test',
      );

      expect(res, isNotNull);
      expect(apiClient.lastRunId, isNotNull);
      expect(apiClient.lastApiLatencyMs, isNotNull);
      expect(apiClient.lastBackendDurationMs, 42.0);
      expect(apiClient.lastUiDurationMs, isNotNull);
    });

    testWidgets('DiagnosticsDialog displays timing breakdown and dynamic footer', (tester) async {
      final mock = MockSteadyDevApiClient(
        mockConfig: TelemetryConfigData(
          enabled: true,
          dsnConfigured: true,
          maskedDsn: 'https://mask***@sentry.io/1',
          exportState: 'local_only',
          verifiedDelivery: false,
        ),
      );
      mock.lastRunId = 'run-test-123';
      mock.lastUiDurationMs = 1250.0;
      mock.lastApiLatencyMs = 450.0;
      mock.lastBackendDurationMs = 800.0;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (ctx) => ElevatedButton(
                onPressed: () => DiagnosticsDialog.show(ctx, apiClient: mock),
                child: const Text('Open'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open'));
      await tester.pumpAndSettle();

      expect(find.text('Cross-Process Timing & Correlation'), findsOneWidget);
      expect(find.textContaining('Run ID: run-test-123'), findsOneWidget);
      expect(find.text('Client UI Duration'), findsOneWidget);
      expect(find.text('1.25s'), findsOneWidget);
      expect(find.text('450ms'), findsOneWidget);
      expect(find.textContaining('Sanitized Sentry Telemetry Active'), findsOneWidget);
    });
  });
}
