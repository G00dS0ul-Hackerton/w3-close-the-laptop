import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:desktop/dialogs/select_model_dialog.dart';
import 'package:desktop/models/session_models.dart';
import 'package:desktop/theme/tokens.dart';

void main() {
  final sampleModels = [
    const ModelOption(
      id: 'gemma3:4b',
      name: 'gemma3:4b',
      displayName: 'Gemma 3 (4B)',
      family: 'gemma3',
      parameterSize: '4.3B',
      quantization: 'Q4_K_M',
      sizeBytes: 3338801804,
      isRecommended: true,
      isRunning: true,
    ),
    const ModelOption(
      id: 'qwen2.5-coder:3b',
      name: 'qwen2.5-coder:3b',
      displayName: 'Qwen 2.5 Coder (3B)',
      family: 'qwen2',
      parameterSize: '3.1B',
      quantization: 'Q4_K_M',
      sizeBytes: 1929912626,
    ),
    const ModelOption(
      id: 'qwen2.5:7b',
      name: 'qwen2.5:7b',
      displayName: 'Qwen 2.5 (7B)',
      family: 'qwen2',
      parameterSize: '7.6B',
      quantization: 'Q4_K_M',
      sizeBytes: 4683087332,
    ),
    const ModelOption(
      id: 'baseline-checklist',
      name: 'baseline-checklist',
      displayName: 'Baseline Checklist (Offline Floor)',
      isBaseline: true,
      isRunning: true,
    ),
  ];

  Widget buildTestHost({
    required List<ModelOption> models,
    required String currentModelId,
    bool isOllamaOffline = false,
    ValueChanged<String?>? onResult,
  }) {
    return MaterialApp(
      theme: ThemeData(
        extensions: const [SteadyDevThemeTokens.light],
      ),
      home: Scaffold(
        body: Builder(
          builder: (context) => ElevatedButton(
            onPressed: () async {
              final res = await SelectModelDialog.show(
                context,
                models: models,
                currentModelId: currentModelId,
                isOllamaOffline: isOllamaOffline,
              );
              onResult?.call(res);
            },
            child: const Text('Open Dialog'),
          ),
        ),
      ),
    );
  }

  testWidgets('SelectModelDialog renders installed models with metadata and recommended tag', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      buildTestHost(
        models: sampleModels,
        currentModelId: 'gemma3:4b',
      ),
    );

    await tester.tap(find.text('Open Dialog'));
    await tester.pumpAndSettle();

    expect(find.text('Select Review Model'), findsOneWidget);
    expect(find.text('Gemma 3 (4B)'), findsOneWidget);
    expect(find.text('Recommended'), findsOneWidget);
    expect(find.text('In RAM'), findsOneWidget);
    expect(find.text('Qwen 2.5 Coder (3B)'), findsOneWidget);
    expect(find.text('Qwen 2.5 (7B)'), findsOneWidget);
    expect(find.text('Baseline Checklist (Offline Floor)'), findsOneWidget);
  });

  testWidgets('Selecting a model and clicking Select Model returns selected model ID', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    String? returnedModel;

    await tester.pumpWidget(
      buildTestHost(
        models: sampleModels,
        currentModelId: 'gemma3:4b',
        onResult: (res) => returnedModel = res,
      ),
    );

    await tester.tap(find.text('Open Dialog'));
    await tester.pumpAndSettle();

    // Tap Qwen 2.5 (7B)
    await tester.tap(find.text('Qwen 2.5 (7B)'));
    await tester.pumpAndSettle();

    // Confirm selection
    await tester.tap(find.text('Select Model'));
    await tester.pumpAndSettle();

    expect(returnedModel, 'qwen2.5:7b');
  });

  testWidgets('SelectModelDialog renders clean offline alert when Ollama is offline', (tester) async {
    tester.view.physicalSize = const Size(1280, 800);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      buildTestHost(
        models: [
          const ModelOption(
            id: 'baseline-checklist',
            name: 'baseline-checklist',
            displayName: 'Baseline Checklist (Offline Floor)',
            isBaseline: true,
          ),
        ],
        currentModelId: 'baseline-checklist',
        isOllamaOffline: true,
      ),
    );

    await tester.tap(find.text('Open Dialog'));
    await tester.pumpAndSettle();

    expect(find.textContaining('Ollama daemon unreachable'), findsOneWidget);
    expect(find.text('Baseline Checklist (Offline Floor)'), findsOneWidget);
  });

  testWidgets('SelectModelDialog adheres to P-6 and avoids RenderFlex overflow in 800x600 viewport', (tester) async {
    tester.view.physicalSize = const Size(800, 600);
    tester.view.devicePixelRatio = 1.0;
    addTearDown(tester.view.resetPhysicalSize);

    await tester.pumpWidget(
      buildTestHost(
        models: sampleModels,
        currentModelId: 'gemma3:4b',
      ),
    );

    await tester.tap(find.text('Open Dialog'));
    await tester.pumpAndSettle();

    // Verify dialog opened without exceptions
    expect(find.byType(SelectModelDialog), findsOneWidget);
    expect(tester.takeException(), isNull);
  });
}
