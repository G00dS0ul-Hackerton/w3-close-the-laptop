import 'package:flutter/material.dart';

import '../models/session_models.dart';
import '../theme/tokens.dart';

class ReasonDialog extends StatefulWidget {
  final FindingItem finding;
  final FindingLifecycle targetStatus;

  const ReasonDialog({
    super.key,
    required this.finding,
    required this.targetStatus,
  });

  static Future<String?> show(
    BuildContext context, {
    required FindingItem finding,
    required FindingLifecycle targetStatus,
  }) {
    return showDialog<String>(
      context: context,
      builder: (ctx) => ReasonDialog(finding: finding, targetStatus: targetStatus),
    );
  }

  @override
  State<ReasonDialog> createState() => _ReasonDialogState();
}

class _ReasonDialogState extends State<ReasonDialog> {
  final _controller = TextEditingController();
  final _formKey = GlobalKey<FormState>();

  String get _title {
    switch (widget.targetStatus) {
      case FindingLifecycle.resolved:
        return 'Mark as resolved';
      case FindingLifecycle.deferred:
        return 'Leave it for later';
      case FindingLifecycle.dismissed:
        return 'Dismiss with context';
      default:
        return 'Add context';
    }
  }

  String get _description {
    switch (widget.targetStatus) {
      case FindingLifecycle.resolved:
        return 'What check or evidence addresses this?';
      case FindingLifecycle.deferred:
        return 'What should tomorrow you know?';
      case FindingLifecycle.dismissed:
        return 'Why is this finding not relevant?';
      default:
        return 'Provide notes for this finding.';
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;

    return Dialog(
      backgroundColor: tokens.panel,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: BorderSide(color: tokens.dividerLine),
      ),
      child: Container(
        constraints: const BoxConstraints(maxWidth: 520),
        child: Form(
          key: _formKey,
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              // Header
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        _title,
                        overflow: TextOverflow.ellipsis,
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: tokens.primaryText,
                        ),
                      ),
                    ),
                    IconButton(
                      icon: Icon(Icons.close, color: tokens.secondaryText),
                      onPressed: () => Navigator.of(context).pop(),
                    ),
                  ],
                ),
              ),
              Divider(height: 1, color: tokens.dividerLine),

              // Body
              Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      _description,
                      style: TextStyle(fontSize: 14, color: tokens.secondaryText),
                    ),
                    const SizedBox(height: 16),
                    TextFormField(
                      controller: _controller,
                      maxLines: 4,
                      maxLength: 600,
                      decoration: InputDecoration(
                        hintText: 'A short note is enough.',
                        hintStyle: TextStyle(color: tokens.secondaryText.withAlpha(150)),
                        filled: true,
                        fillColor: tokens.canvas,
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(color: tokens.inputBoundary),
                        ),
                        focusedBorder: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(8),
                          borderSide: BorderSide(color: tokens.brandAction, width: 2),
                        ),
                      ),
                      validator: (val) {
                        if (val == null || val.trim().isEmpty) {
                          return 'Context note is required.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'This changes the finding’s status only. It does not verify or modify a real project.',
                      style: TextStyle(fontSize: 12, color: tokens.secondaryText),
                    ),
                  ],
                ),
              ),
              Divider(height: 1, color: tokens.dividerLine),

              // Actions
              Padding(
                padding: const EdgeInsets.all(16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.end,
                  children: [
                    TextButton(
                      onPressed: () => Navigator.of(context).pop(),
                      child: Text('Cancel', style: TextStyle(color: tokens.secondaryText)),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton(
                      style: ElevatedButton.styleFrom(
                        backgroundColor: tokens.brandAction,
                        foregroundColor: tokens.brandActionInk,
                        padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                      onPressed: () {
                        if (_formKey.currentState?.validate() ?? false) {
                          Navigator.of(context).pop(_controller.text.trim());
                        }
                      },
                      child: Text(_title),
                    ),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
