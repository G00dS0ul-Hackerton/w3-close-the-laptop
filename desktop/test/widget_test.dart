import 'package:desktop/main.dart';
import 'package:desktop/theme/theme_manager.dart';
import 'package:desktop/views/session_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('SteadyDev main scaffold renders brand and session view', (
    tester,
  ) async {
    final themeManager = ThemeManager();
    await tester.pumpWidget(SteadyDevApp(themeManager: themeManager));
    await tester.pumpAndSettle();

    // Verify Brand title
    expect(find.text('SteadyDev'), findsOneWidget);
    expect(find.text('Close the Laptop'), findsOneWidget);

    // Verify Session view heading
    expect(find.text('Stay in flow. Keep the thread.'), findsOneWidget);
    expect(find.text('Worth a second look'), findsOneWidget);

    // Verify Today's Intention
    expect(find.text('TODAY’S INTENTION'), findsOneWidget);
    expect(
      find.text(
        'Fix the login redirect and make the dashboard work on mobile.',
      ),
      findsOneWidget,
    );
  });

  testWidgets('Navigation switches between Session, Audit, and Closing views', (
    tester,
  ) async {
    final themeManager = ThemeManager();
    await tester.pumpWidget(SteadyDevApp(themeManager: themeManager));
    await tester.pumpAndSettle();

    // Navigate to Quiet audit
    await tester.tap(find.text('Quiet audit'));
    await tester.pumpAndSettle();
    expect(find.text('EVIDENCE, NOT ASSUMPTIONS'), findsOneWidget);
    expect(find.text('A small, honest second look.'), findsOneWidget);

    // Navigate to Closing card
    await tester.tap(find.text('Closing card'));
    await tester.pumpAndSettle();
    expect(find.text('LEAVE THE WORK. KEEP THE CONTEXT.'), findsOneWidget);
    expect(find.text('A good place to stop.'), findsOneWidget);
    expect(find.text('What you can leave here'), findsOneWidget);
    expect(find.text('Start here, not from scratch.'), findsOneWidget);

    // Back to session via button
    final backBtn = find.text('Back to session');
    await tester.ensureVisible(backBtn);
    await tester.tap(backBtn);
    await tester.pumpAndSettle();
    expect(find.text('Stay in flow. Keep the thread.'), findsOneWidget);
  });

  testWidgets('Intention editing dialog updates session intention text', (
    tester,
  ) async {
    final themeManager = ThemeManager();
    await tester.pumpWidget(SteadyDevApp(themeManager: themeManager));
    await tester.pumpAndSettle();

    // Tap pencil icon on intention card
    await tester.tap(find.byTooltip('Edit session intention'));
    await tester.pumpAndSettle();

    // Verify dialog open
    expect(find.text('What matters this session?'), findsOneWidget);
    expect(find.text('Session intention'), findsOneWidget);

    // Enter updated intention
    await tester.enterText(
      find.byType(TextFormField),
      'Ship real Flutter vertical slice today',
    );
    await tester.tap(find.text('Update intention'));
    await tester.pumpAndSettle();

    // Verify updated on session card
    expect(find.text('Ship real Flutter vertical slice today'), findsOneWidget);
  });

  testWidgets('Evidence dialog opens with locator and disclaimers', (
    tester,
  ) async {
    final themeManager = ThemeManager();
    await tester.pumpWidget(SteadyDevApp(themeManager: themeManager));
    await tester.pumpAndSettle();

    // Tap "View evidence" on the first finding card
    final viewEvidence = find.text('View evidence').first;
    await tester.ensureVisible(viewEvidence);
    await tester.tap(viewEvidence);
    await tester.pumpAndSettle();

    // Verify Evidence dialog
    expect(find.text('Evidence behind the finding'), findsOneWidget);
    expect(
      find.text('Scoped evidence · bound to current working snapshot'),
      findsOneWidget,
    );
    expect(find.text('Limits of this finding'), findsOneWidget);

    // Close dialog
    await tester.tap(find.byTooltip('Close evidence'));
    await tester.pumpAndSettle();
    expect(find.text('Evidence behind the finding'), findsNothing);
  });

  testWidgets(
    'Responsive layout renders cleanly at 600px width without overflow',
    (tester) async {
      final themeManager = ThemeManager();
      tester.view.physicalSize = const Size(600, 900);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);

      await tester.pumpWidget(SteadyDevApp(themeManager: themeManager));
      await tester.pumpAndSettle();

      // Expect no RenderFlex overflow errors thrown
      expect(tester.takeException(), isNull);
      expect(find.text('Stay in flow. Keep the thread.'), findsOneWidget);
    },
  );

  testWidgets(
    'SessionView displays Stop button during active review and triggers cancel',
    (tester) async {
      bool cancelCalled = false;

      await tester.pumpWidget(
        MaterialApp(
          home: Scaffold(
            body: SingleChildScrollView(
              child: SessionView(
                repoName: 'test-repo',
                intention: 'Testing stop button',
                criteria: const ['Pass'],
                findings: const [],
                receipts: const [],
                quietStatus: 'Reviewing...',
                isReviewing: true,
                isEnded: false,
                isPaused: false,
                isCleanWorkingTree: false,
                isEngineOffline: false,
                activeEngine: 'Gemma 3 (4B)',
                onSelectRepo: () {},
                onTriggerCheckpoint: () {},
                onTogglePause: () {},
                onNavigateToClosing: () {},
                onUpdateIntention: (_) {},
                onUpdateFindingStatus: (_, __, [___]) {},
                onCancelReview: () => cancelCalled = true,
              ),
            ),
          ),
        ),
      );
      await tester.pump();
      await tester.pump(const Duration(milliseconds: 100));

      expect(find.byIcon(Icons.stop), findsOneWidget);
      await tester.tap(find.byIcon(Icons.stop));
      await tester.pump();
      expect(cancelCalled, isTrue);
    },
  );
}
