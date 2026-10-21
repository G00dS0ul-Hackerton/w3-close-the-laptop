import 'package:flutter/material.dart';

import '../models/session_models.dart';
import '../theme/tokens.dart';

class EvidenceDialog extends StatelessWidget {
  final FindingItem finding;

  const EvidenceDialog({super.key, required this.finding});

  static Future<void> show(BuildContext context, FindingItem finding) {
    return showDialog(
      context: context,
      builder: (ctx) => EvidenceDialog(finding: finding),
    );
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
        constraints: const BoxConstraints(maxWidth: 580, maxHeight: 600),
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
                      'Evidence behind the finding',
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
                    tooltip: 'Close evidence',
                  ),
                ],
              ),
            ),
            Divider(height: 1, color: tokens.dividerLine),

            // Scrollable Content
            Flexible(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Disclaimer banner
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      decoration: BoxDecoration(
                        color: tokens.softBrandSurface,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: tokens.brandOutline),
                      ),
                      child: Row(
                        children: [
                          Icon(Icons.shield_outlined, size: 18, color: tokens.brandAction),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              'Scoped evidence · bound to current working snapshot',
                              style: TextStyle(fontSize: 13, color: tokens.brandAction, fontWeight: FontWeight.w500),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Locator
                    Text(
                      finding.locator,
                      style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: tokens.secondaryText),
                    ),
                    const SizedBox(height: 8),

                    // Code / Diff excerpt
                    if (finding.receiptSnippet != null && finding.receiptSnippet!.isNotEmpty) ...[
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: tokens.subtleSurface,
                          borderRadius: BorderRadius.circular(8),
                          border: Border.all(color: tokens.dividerLine),
                        ),
                        child: SelectableText(
                          finding.receiptSnippet!,
                          style: TextStyle(
                            fontFamily: 'Consolas',
                            fontSize: 13,
                            color: tokens.primaryText,
                            height: 1.5,
                          ),
                        ),
                      ),
                      const SizedBox(height: 16),
                    ],

                    // Limits of this finding
                    Text(
                      'Limits of this finding',
                      style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: tokens.primaryText),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      finding.limit ??
                          'This is an evidence gap, not a confirmed bug. You may have verified it outside this tool.',
                      style: TextStyle(fontSize: 14, color: tokens.secondaryText, height: 1.4),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
