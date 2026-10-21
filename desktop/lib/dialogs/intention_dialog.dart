import 'package:flutter/material.dart';

import '../theme/tokens.dart';

class IntentionDialog extends StatefulWidget {
  final String currentIntention;

  const IntentionDialog({super.key, required this.currentIntention});

  static Future<String?> show(BuildContext context, String currentIntention) {
    return showDialog<String>(
      context: context,
      builder: (ctx) => IntentionDialog(currentIntention: currentIntention),
    );
  }

  @override
  State<IntentionDialog> createState() => _IntentionDialogState();
}

class _IntentionDialogState extends State<IntentionDialog> {
  late final TextEditingController _controller;
  final _formKey = GlobalKey<FormState>();

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.currentIntention);
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
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 18),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        'What matters this session?',
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
              Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      'Session intention',
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: tokens.primaryText),
                    ),
                    const SizedBox(height: 12),
                    TextFormField(
                      controller: _controller,
                      maxLines: 3,
                      maxLength: 220,
                      decoration: InputDecoration(
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
                          return 'Session intention cannot be empty.';
                        }
                        return null;
                      },
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'This edits the session intention. Changes and checks will be compared against this intention.',
                      style: TextStyle(fontSize: 12, color: tokens.secondaryText),
                    ),
                  ],
                ),
              ),
              Divider(height: 1, color: tokens.dividerLine),
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
                      child: const Text('Update intention'),
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
