import 'package:desktop/main.dart';
import 'package:desktop/models/session_models.dart';
import 'package:desktop/theme/theme_manager.dart';
import 'package:desktop/views/audit_view.dart';
import 'package:desktop/views/closing_view.dart';
import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  testWidgets('Restart note survives navigation tab switching without loss', (tester) async {
    final themeManager = ThemeManager(persistToDisk: false);
    await tester.pumpWidget(SteadyDevApp(themeManager: themeManager));
    await tester.pumpAndSettle();

    // 1. Navigate to Closing card
    await tester.tap(find.text('Closing card'));
    await tester.pumpAndSettle();

    // Verify initial note exists
    expect(find.text('A GIFT TO TOMORROW YOU'), findsOneWidget);
    final noteField = find.byType(TextFormField);
    expect(noteField, findsOneWidget);

    // 2. User edits the restart note
    const customUserNote = 'Verify mobile navigation at 390px tomorrow morning with auth test.';
    await tester.enterText(noteField, customUserNote);
    await tester.pumpAndSettle();

    // 3. Switch back to Session view
    final backBtn = find.text('Back to session');
    await tester.ensureVisible(backBtn);
    await tester.tap(backBtn);
    await tester.pumpAndSettle();
    expect(find.text('Stay in flow. Keep the thread.'), findsOneWidget);

    // 4. Switch back to Closing card
    await tester.tap(find.text('Closing card'));
    await tester.pumpAndSettle();

    // Verify user note was NOT discarded on view unmount
    expect(find.text(customUserNote), findsOneWidget);
  });

  testWidgets('Restart note survives theme switching independently', (tester) async {
    final themeManager = ThemeManager(persistToDisk: false);
    await tester.pumpWidget(SteadyDevApp(themeManager: themeManager));
    await tester.pumpAndSettle();

    // Navigate to Closing card and type note
    await tester.tap(find.text('Closing card'));
    await tester.pumpAndSettle();

    const customUserNote = 'Ensure WAL checkpoint truncate executes cleanly.';
    await tester.enterText(find.byType(TextFormField), customUserNote);
    await tester.pump();

    // Toggle theme: Light -> Dark
    await themeManager.setThemeMode(ThemeMode.dark);
    await tester.pump();

    // Verify note is still preserved in Dark theme
    expect(find.text(customUserNote), findsOneWidget);

    // Toggle theme: Dark -> Light
    await themeManager.setThemeMode(ThemeMode.light);
    await tester.pump();

    // Verify note is still preserved in Light theme
    expect(find.text(customUserNote), findsOneWidget);
  });

  testWidgets('Leave it here passes edited note and marks session closed', (tester) async {
    String? passedNote;
    bool finalized = false;

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: ClosingView(
            findings: const [],
            receipts: [
              SessionCheckReceipt(
                id: 'r-1',
                command: 'pytest',
                exitCode: 0,
                output: '1 passed',
                timestampUtc: 'now',
              )
            ],
            changedFileCount: 2,
            initialRestartNote: 'Initial note text',
            isEnded: false,
            onBackToSession: () {},
            onFinalizeSession: (note) {
              passedNote = note;
              finalized = true;
            },
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Verify dynamic What you can leave here
    expect(find.textContaining('1 check(s) passing in local verification receipts'), findsOneWidget);
    expect(find.textContaining('2 file(s) safely bound to working snapshot'), findsOneWidget);

    // Edit note
    await tester.enterText(find.byType(TextFormField), 'Updated final note before leaving');
    await tester.pump();

    // Click "Leave it here"
    final leaveBtn = find.text('Leave it here');
    await tester.ensureVisible(leaveBtn);
    await tester.tap(leaveBtn);
    await tester.pump();

    expect(finalized, isTrue);
    expect(passedNote, equals('Updated final note before leaving'));
  });

  testWidgets('AuditView renders EVIDENCE-RETIRED and STALE LOCATOR badges', (tester) async {
    final findings = [
      FindingItem(
        id: 'f-retired',
        title: 'Auth error assertion check',
        description: 'Verified by receipt rcpt-001',
        locator: 'tests/auth_test.py:42',
        type: FindingType.confirmed,
        lifecycle: FindingLifecycle.evidenceRetired,
        retiredByReceiptId: 'rcpt-001',
      ),
      FindingItem(
        id: 'f-stale',
        title: 'Old helper check',
        description: 'File was deleted from repository',
        locator: 'src/deleted_helper.py:10',
        type: FindingType.unverified,
        lifecycle: FindingLifecycle.open,
        isStale: true,
        staleReason: "File 'src/deleted_helper.py' was deleted or moved from disk",
      ),
    ];

    await tester.pumpWidget(
      MaterialApp(
        home: Scaffold(
          body: AuditView(
            findings: findings,
            onUpdateFindingStatus: (_, __, ___) {},
          ),
        ),
      ),
    );
    await tester.pumpAndSettle();

    // Filter to 'All findings'
    await tester.tap(find.text('All findings'));
    await tester.pumpAndSettle();

    expect(find.text('EVIDENCE-RETIRED'), findsOneWidget);
    expect(find.text('STALE LOCATOR'), findsOneWidget);
    expect(find.textContaining("File 'src/deleted_helper.py' was deleted"), findsOneWidget);
  });
}
