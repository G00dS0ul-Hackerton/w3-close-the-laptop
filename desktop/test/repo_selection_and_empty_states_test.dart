import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:desktop/dialogs/select_repo_dialog.dart';
import 'package:desktop/models/session_models.dart';
import 'package:desktop/theme/theme_manager.dart';
import 'package:desktop/views/session_view.dart';
import 'package:desktop/widgets/steady_dev_scaffold.dart';

void main() {
  testWidgets(
    'SelectRepoDialog displays error for nonexistent directory path',
    (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: Builder(
              builder: (context) => ElevatedButton(
                onPressed: () => SelectRepoDialog.show(context),
                child: const Text('Open Dialog'),
              ),
            ),
          ),
        ),
      );

      await tester.tap(find.text('Open Dialog'));
      await tester.pumpAndSettle();

      expect(find.text('Select Repository'), findsOneWidget);
      await tester.enterText(
        find.byType(TextField),
        'C:\\nonexistent\\path\\to\\dir_12345',
      );
      await tester.tap(find.text('Open repository'));
      await tester.pumpAndSettle();

      expect(find.text('Directory does not exist'), findsOneWidget);
    },
  );

  testWidgets(
    'Clicking workspace header breadcrumb opens repository picker dialog',
    (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      final themeManager = ThemeManager(persistToDisk: false);
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(body: SteadyDevScaffold(themeManager: themeManager)),
        ),
      );
      await tester.pumpAndSettle();

      // Verify initial breadcrumb
      expect(find.text('sample-project'), findsOneWidget);

      // Tap breadcrumb
      await tester.tap(find.text('sample-project'));
      await tester.pumpAndSettle();

      // SelectRepoDialog should be visible
      expect(find.text('Select Repository'), findsOneWidget);
      expect(find.text('Open repository'), findsOneWidget);
    },
  );

  testWidgets(
    'SessionView displays CleanWorkingTreeCard when working tree is clean',
    (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SessionView(
              repoName: 'clean-repo',
              intention: 'Test clean repository',
              criteria: const ['Criterion 1'],
              findings: const [],
              isReviewing: false,
              isPaused: false,
              isEnded: false,
              quietStatus: 'Ready for checkpoint',
              isCleanWorkingTree: true,
              onTriggerCheckpoint: () {},
              onTogglePause: () {},
              onNavigateToClosing: () {},
              onUpdateIntention: (_) {},
              onUpdateFindingStatus: (_, __, ___) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('Working tree clean'), findsOneWidget);
      expect(
        find.text('No uncommitted code changes detected in this repository.'),
        findsOneWidget,
      );
    },
  );

  testWidgets(
    'SessionView displays ReviewLoadingCard during active review inference',
    (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SessionView(
              repoName: 'sample-project',
              intention: 'Inference test',
              criteria: const ['Criterion 1'],
              findings: const [],
              isReviewing: true,
              isPaused: false,
              isEnded: false,
              quietStatus: 'Reviewing snapshot with Ollama...',
              onTriggerCheckpoint: () {},
              onTogglePause: () {},
              onNavigateToClosing: () {},
              onUpdateIntention: (_) {},
              onUpdateFindingStatus: (_, __, ___) {},
            ),
          ),
        ),
      );
      // Indeterminate progress indicators animate continuously; use pump instead of pumpAndSettle
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(
        find.text('Reviewing working snapshot with local model...'),
        findsOneWidget,
      );
      expect(find.byType(LinearProgressIndicator), findsOneWidget);
    },
  );

  testWidgets(
    'SessionView displays EngineOfflineBanner when engine is offline',
    (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      bool retryCalled = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SessionView(
              repoName: 'sample-project',
              intention: 'Offline test',
              criteria: const ['Criterion 1'],
              findings: const [],
              isReviewing: false,
              isPaused: false,
              isEnded: false,
              quietStatus: 'Engine offline',
              isEngineOffline: true,
              onRetryConnection: () => retryCalled = true,
              onTriggerCheckpoint: () {},
              onTogglePause: () {},
              onNavigateToClosing: () {},
              onUpdateIntention: (_) {},
              onUpdateFindingStatus: (_, __, ___) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(
        find.textContaining('SteadyDev local engine is offline'),
        findsOneWidget,
      );
      expect(find.text('Retry'), findsOneWidget);

      await tester.tap(find.text('Retry'));
      await tester.pump();
      expect(retryCalled, isTrue);
    },
  );

  testWidgets(
    'SessionView displays truthful empty state when receipts list is empty',
    (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SessionView(
              repoName: 'sample-project',
              intention: 'Receipts test',
              criteria: const ['Criterion 1'],
              findings: const [],
              receipts: const [],
              isReviewing: false,
              isPaused: false,
              isEnded: false,
              quietStatus: 'Ready for checkpoint',
              onTriggerCheckpoint: () {},
              onTogglePause: () {},
              onNavigateToClosing: () {},
              onUpdateIntention: (_) {},
              onUpdateFindingStatus: (_, __, ___) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.text('What has evidence'), findsOneWidget);
      expect(find.text('No checks recorded yet'), findsOneWidget);
      expect(find.text('Auth checks'), findsNothing);
    },
  );

  testWidgets('Clicking New session button opens confirmation dialog', (
    tester,
  ) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    final themeManager = ThemeManager(persistToDisk: false);
    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(body: SteadyDevScaffold(themeManager: themeManager)),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('New session'), findsOneWidget);
    await tester.tap(find.text('New session'));
    await tester.pumpAndSettle();

    expect(find.text('Start a new session?'), findsOneWidget);
    expect(find.text('Start fresh'), findsOneWidget);
  });

  test('ReviewResultData deserializes model_name key into modelTag', () {
    final json = {
      'packet_id': 'pkt-test',
      'model_name': 'gemma3:4b',
      'elapsed_seconds': 28.5,
      'status': 'clean',
      'findings': [],
      'closing_summary': 'Summary',
      'restart_note': 'Restart note',
      'retired_finding_ids': [],
    };
    final data = ReviewResultData.fromJson(json);
    expect(data.modelTag, 'gemma3:4b');
  });

  testWidgets(
    'SessionView displays active engine tier badges for Gemma, Qwen fallback, and Baseline',
    (tester) async {
      tester.view.physicalSize = const Size(1280, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      // 1. Gemma 3 Primary
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SessionView(
              repoName: 'sample-project',
              intention: 'Gemma test',
              criteria: const ['Criterion 1'],
              findings: const [],
              isReviewing: false,
              isPaused: false,
              isEnded: false,
              quietStatus: 'Checkpoint complete',
              activeEngine: 'gemma3:4b',
              onTriggerCheckpoint: () {},
              onTogglePause: () {},
              onNavigateToClosing: () {},
              onUpdateIntention: (_) {},
              onUpdateFindingStatus: (_, __, ___) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Gemma 3 (4B)'), findsOneWidget);

      // 2. Qwen Fallback
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SessionView(
              repoName: 'sample-project',
              intention: 'Qwen test',
              criteria: const ['Criterion 1'],
              findings: const [],
              isReviewing: false,
              isPaused: false,
              isEnded: false,
              quietStatus: 'Checkpoint complete',
              activeEngine: 'qwen2.5-coder:3b',
              onTriggerCheckpoint: () {},
              onTogglePause: () {},
              onNavigateToClosing: () {},
              onUpdateIntention: (_) {},
              onUpdateFindingStatus: (_, __, ___) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Qwen 2.5 Coder (Fallback)'), findsOneWidget);

      // 3. Baseline Checklist Safety Floor
      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SessionView(
              repoName: 'sample-project',
              intention: 'Baseline test',
              criteria: const ['Criterion 1'],
              findings: const [],
              isReviewing: false,
              isPaused: false,
              isEnded: false,
              quietStatus: 'Checkpoint complete',
              activeEngine: 'gemma3:4b-fallback-baseline',
              onTriggerCheckpoint: () {},
              onTogglePause: () {},
              onNavigateToClosing: () {},
              onUpdateIntention: (_) {},
              onUpdateFindingStatus: (_, __, ___) {},
            ),
          ),
        ),
      );
      await tester.pumpAndSettle();
      expect(find.text('Baseline Checklist'), findsOneWidget);
    },
  );
}
