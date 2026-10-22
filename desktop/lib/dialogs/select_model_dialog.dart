import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import '../models/session_models.dart';
import '../theme/tokens.dart';

class SelectModelDialog extends StatefulWidget {
  final List<ModelOption> models;
  final String currentModelId;
  final bool isOllamaOffline;

  const SelectModelDialog({
    super.key,
    required this.models,
    required this.currentModelId,
    this.isOllamaOffline = false,
  });

  static Future<String?> show(
    BuildContext context, {
    required List<ModelOption> models,
    required String currentModelId,
    bool isOllamaOffline = false,
  }) {
    return showDialog<String>(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => SelectModelDialog(
        models: models,
        currentModelId: currentModelId,
        isOllamaOffline: isOllamaOffline,
      ),
    );
  }

  @override
  State<SelectModelDialog> createState() => _SelectModelDialogState();
}

class _SelectModelDialogState extends State<SelectModelDialog> {
  late String _selectedId;

  @override
  void initState() {
    super.initState();
    _selectedId = widget.currentModelId;
    // If current model not in list and list has models, fallback to first or baseline
    final exists = widget.models.any((m) => m.id == _selectedId);
    if (!exists && widget.models.isNotEmpty) {
      final rec = widget.models.firstWhere(
        (m) => m.isRecommended,
        orElse: () => widget.models.first,
      );
      _selectedId = rec.id;
    }
  }

  String _formatBytes(int bytes) {
    if (bytes <= 0) return '';
    final gb = bytes / (1024 * 1024 * 1024);
    return '${gb.toStringAsFixed(1)} GB';
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;

    return Focus(
      autofocus: true,
      onKeyEvent: (node, event) {
        if (event is KeyDownEvent) {
          if (event.logicalKey == LogicalKeyboardKey.escape) {
            Navigator.of(context).pop();
            return KeyEventResult.handled;
          } else if (event.logicalKey == LogicalKeyboardKey.enter) {
            Navigator.of(context).pop(_selectedId);
            return KeyEventResult.handled;
          }
        }
        return KeyEventResult.ignored;
      },
      child: Dialog(
        backgroundColor: tokens.panel,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(12),
          side: BorderSide(color: tokens.dividerLine),
        ),
        child: ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: 520, maxHeight: 600),
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Header
                Row(
                  children: [
                    Icon(Icons.tune, size: 20, color: tokens.brandAction),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'Select Review Model',
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: tokens.primaryText,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 6),
                Text(
                  'Choose which local open-weight model or offline baseline reviews your checkpoints.',
                  style: TextStyle(fontSize: 13, color: tokens.secondaryText),
                ),
                const SizedBox(height: 16),

                // Offline alert if Ollama unreachable
                if (widget.isOllamaOffline) ...[
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: tokens.badgeJudgmentBg,
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: tokens.badgeJudgmentText.withValues(alpha: 0.3)),
                    ),
                    child: Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Icon(Icons.warning_amber_rounded, size: 18, color: tokens.badgeJudgmentText),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'Ollama daemon unreachable at 127.0.0.1:11434. Only Baseline Checklist is available until Ollama is started.',
                            style: TextStyle(
                              fontSize: 12,
                              color: tokens.badgeJudgmentText,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 14),
                ],

                // Model list
                Flexible(
                  child: ListView.separated(
                    shrinkWrap: true,
                    itemCount: widget.models.length,
                    separatorBuilder: (ctx, i) => const SizedBox(height: 8),
                    itemBuilder: (ctx, i) {
                      final model = widget.models[i];
                      final isSelected = model.id == _selectedId;

                      return InkWell(
                        onTap: () {
                          setState(() => _selectedId = model.id);
                        },
                        borderRadius: BorderRadius.circular(8),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                          decoration: BoxDecoration(
                            color: isSelected
                                ? tokens.softBrandSurface
                                : tokens.subtleSurface.withValues(alpha: 0.3),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: isSelected
                                  ? tokens.brandAction
                                  : tokens.dividerLine,
                              width: isSelected ? 1.5 : 1.0,
                            ),
                          ),
                          child: Row(
                            crossAxisAlignment: CrossAxisAlignment.center,
                            children: [
                              // Radio indicator
                              Icon(
                                isSelected
                                    ? Icons.radio_button_checked
                                    : Icons.radio_button_off,
                                size: 18,
                                color: isSelected
                                    ? tokens.brandAction
                                    : tokens.secondaryText,
                              ),
                              const SizedBox(width: 12),

                              // Model info
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    // Title row with recommended chip
                                    Wrap(
                                      spacing: 6,
                                      runSpacing: 4,
                                      crossAxisAlignment: WrapCrossAlignment.center,
                                      children: [
                                        Text(
                                          model.displayName,
                                          style: TextStyle(
                                            fontSize: 14,
                                            fontWeight: FontWeight.w600,
                                            color: isSelected
                                                ? tokens.primaryText
                                                : tokens.primaryText.withValues(alpha: 0.85),
                                          ),
                                        ),
                                        if (model.isRecommended)
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: tokens.softBrandSurface,
                                              borderRadius: BorderRadius.circular(4),
                                              border: Border.all(color: tokens.brandAction.withValues(alpha: 0.4)),
                                            ),
                                            child: Text(
                                              'Recommended',
                                              style: TextStyle(
                                                fontSize: 10,
                                                fontWeight: FontWeight.bold,
                                                color: tokens.brandAction,
                                              ),
                                            ),
                                          ),
                                      ],
                                    ),
                                    const SizedBox(height: 4),

                                    // Metadata chips wrap
                                    Wrap(
                                      spacing: 6,
                                      runSpacing: 4,
                                      children: [
                                        if (model.isBaseline)
                                          _buildTag(tokens, 'Deterministic Heuristics')
                                        else ...[
                                          if (model.parameterSize.isNotEmpty)
                                            _buildTag(tokens, model.parameterSize),
                                          if (model.family.isNotEmpty)
                                            _buildTag(tokens, model.family),
                                          if (model.sizeBytes > 0)
                                            _buildTag(tokens, _formatBytes(model.sizeBytes)),
                                          if (model.isRunning)
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                              decoration: BoxDecoration(
                                                color: tokens.softBrandSurface,
                                                borderRadius: BorderRadius.circular(4),
                                              ),
                                              child: Row(
                                                mainAxisSize: MainAxisSize.min,
                                                children: [
                                                  Container(
                                                    width: 6,
                                                    height: 6,
                                                    decoration: BoxDecoration(
                                                      color: tokens.brandAction,
                                                      shape: BoxShape.circle,
                                                    ),
                                                  ),
                                                  const SizedBox(width: 4),
                                                  Text(
                                                    'In RAM',
                                                    style: TextStyle(
                                                      fontSize: 10,
                                                      fontWeight: FontWeight.w600,
                                                      color: tokens.brandAction,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ),
                                        ],
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            ],
                          ),
                        ),
                      );
                    },
                  ),
                ),
                const SizedBox(height: 20),

                // Footer Actions
                Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      style: TextButton.styleFrom(
                        foregroundColor: tokens.secondaryText,
                        minimumSize: const Size(44, 44),
                      ),
                      onPressed: () => Navigator.of(context).pop(),
                      child: const Text('Cancel'),
                    ),
                    const SizedBox(width: 12),
                    ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: tokens.brandAction,
                        foregroundColor: tokens.brandActionInk,
                        elevation: 0,
                        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                        minimumSize: const Size(44, 44),
                      ),
                      onPressed: () => Navigator.of(context).pop(_selectedId),
                      child: const Text(
                        'Select Model',
                        style: TextStyle(fontWeight: FontWeight.bold),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildTag(SteadyDevThemeTokens tokens, String label) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: tokens.subtleSurface,
        borderRadius: BorderRadius.circular(4),
        border: Border.all(color: tokens.dividerLine),
      ),
      child: Text(
        label,
        style: TextStyle(fontSize: 10, color: tokens.secondaryText),
      ),
    );
  }
}
