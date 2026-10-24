import 'package:desktop/models/session_models.dart';
import 'package:desktop/theme/tokens.dart';
import 'package:desktop/views/diagnostics_dialog.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  Widget buildTestDialog(ReviewDiagnosticsData data) {
    return MaterialApp(
      theme: ThemeData.light().copyWith(
        extensions: [SteadyDevThemeTokens.light],
      ),
      home: Scaffold(
        body: DiagnosticsDialog(
          initialData: data,
        ),
      ),
    );
  }

  final sampleData = ReviewDiagnosticsData(
    reviewId: 'job-a1b2c3d4',
    phase: 'completed',
    isReviewing: false,
    repoName: 'w3-close-the-laptop',
    snapshotHash: '808f36fbae198184',
    totalFiles: 2,
    totalChunks: 1,
    currentChunk: 1,
    currentFiles: ['desktop/lib/models/session_models.dart'],
    chunkDiagnostics: [
      ChunkProvenanceData(
        chunkIndex: 1,
        totalChunks: 1,
        filePaths: ['desktop/lib/models/session_models.dart'],
        attempts: [
          ModelAttemptData(
            model: 'gemma3:4b',
            outcome: 'timeout',
            durationMs: 147000.0,
            inputTokens: 1948,
            outputTokens: 100,
            doneReason: 'length',
            errorDetail: 'Context length exceeded at 2048 tokens',
          ),
          ModelAttemptData(
            model: 'qwen2.5-coder:3b',
            outcome: 'success',
            durationMs: 32000.0,
            inputTokens: 1779,
            outputTokens: 149,
            doneReason: 'stop',
          ),
        ],
        resolvedEngine: 'qwen2.5-coder:3b',
        fallbackReason: 'Primary model timeout_fallback',
        findingsCount: 1,
      ),
    ],
    elapsedMs: 179000.0,
    deadlineSeconds: 180.0,
    deadlineExceeded: false,
    status: 'clean',
    createdAt: '2026-10-23T18:17:25Z',
    updatedAt: '2026-10-23T18:20:24Z',
  );

  testWidgets('DiagnosticsDialog renders completed review lifecycle, deadline, and chunk matrix cleanly', (
    tester,
  ) async {
    await tester.pumpWidget(buildTestDialog(sampleData));
    await tester.pumpAndSettle();

    // Verify Title
    expect(find.text('Review Diagnostics'), findsOneWidget);

    // Verify Lifecycle Phase
    expect(find.text('COMPLETED'), findsOneWidget);

    // Verify Deadline tracking
    expect(find.textContaining('Workflow Deadline (179.0s / 180s)'), findsOneWidget);
    expect(find.text('1.0s remaining'), findsOneWidget);

    // Verify Chunk & Engine
    expect(find.text('Chunk 1 of 1'), findsOneWidget);
    expect(find.text('Qwen 2.5 Coder 3B'), findsOneWidget);

    // Verify Model attempts
    expect(find.textContaining('gemma3:4b: timeout'), findsOneWidget);
    expect(find.textContaining('qwen2.5-coder:3b: success'), findsOneWidget);

    // Verify Offline badge
    expect(
      find.text('100% Local Diagnostics · Zero Network Egress · Independent of Sentry'),
      findsOneWidget,
    );
  });

  testWidgets('DiagnosticsDialog renders deadline exceeded warning when deadline hit', (
    tester,
  ) async {
    final timeoutData = ReviewDiagnosticsData(
      reviewId: 'job-deadbeef',
      phase: 'timed_out',
      isReviewing: false,
      repoName: 'w3-close-the-laptop',
      totalFiles: 4,
      totalChunks: 2,
      currentChunk: 1,
      currentFiles: [],
      chunkDiagnostics: [],
      elapsedMs: 180500.0,
      deadlineSeconds: 180.0,
      deadlineExceeded: true,
      status: 'fallback_baseline',
      error: 'Workflow deadline exceeded',
      createdAt: '2026-10-23T18:17:25Z',
      updatedAt: '2026-10-23T18:20:25Z',
    );

    await tester.pumpWidget(buildTestDialog(timeoutData));
    await tester.pumpAndSettle();

    expect(find.text('TIMED_OUT'), findsOneWidget);
    expect(find.text('EXCEEDED'), findsOneWidget);
    expect(find.textContaining('Workflow deadline exceeded'), findsOneWidget);
  });

  testWidgets('DiagnosticsDialog renders Unlimited workflow timeout budget cleanly without fixed deadline', (
    tester,
  ) async {
    final unlimitedData = ReviewDiagnosticsData(
      reviewId: 'job-unlimited-01',
      phase: 'auditing',
      isReviewing: true,
      repoName: 'w3-close-the-laptop',
      totalFiles: 3,
      totalChunks: 2,
      currentChunk: 1,
      currentFiles: ['desktop/lib/views/session_view.dart'],
      chunkDiagnostics: [],
      elapsedMs: 45200.0,
      deadlineSeconds: null,
      deadlineExceeded: false,
      status: 'reviewing',
      createdAt: '2026-10-24T20:00:00Z',
      updatedAt: '2026-10-24T20:00:45Z',
    );

    await tester.pumpWidget(buildTestDialog(unlimitedData));
    await tester.pump(const Duration(milliseconds: 100));

    expect(find.text('AUDITING'), findsOneWidget);
    expect(find.textContaining('Workflow Budget (45.2s / Unlimited)'), findsOneWidget);
    expect(find.text('No timeout limit'), findsOneWidget);
  });

  testWidgets('DiagnosticsDialog layout renders cleanly at 600px width without overflow', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(600, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(() => tester.view.resetPhysicalSize());

    await tester.pumpWidget(buildTestDialog(sampleData));
    await tester.pumpAndSettle();

    expect(tester.takeException(), isNull);
  });
}
