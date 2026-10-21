import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../dialogs/evidence_dialog.dart';
import '../models/session_models.dart';
import '../theme/tokens.dart';

class ClosingView extends StatefulWidget {
  final List<FindingItem> findings;
  final String initialRestartNote;
  final bool isEnded;
  final VoidCallback onBackToSession;
  final VoidCallback onFinalizeSession;

  const ClosingView({
    super.key,
    required this.findings,
    required this.initialRestartNote,
    this.isEnded = false,
    required this.onBackToSession,
    required this.onFinalizeSession,
  });

  @override
  State<ClosingView> createState() => _ClosingViewState();
}

class _ClosingViewState extends State<ClosingView> {
  late final TextEditingController _noteController;
  bool _noteEdited = false;
  bool _copied = false;

  @override
  void initState() {
    super.initState();
    _noteController = TextEditingController(text: widget.initialRestartNote);
  }

  @override
  void dispose() {
    _noteController.dispose();
    super.dispose();
  }

  void _copyNote() {
    Clipboard.setData(ClipboardData(text: _noteController.text));
    setState(() => _copied = true);
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Restart note copied to clipboard.'), duration: Duration(seconds: 2)),
    );
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;
    final looseEnds = widget.findings
        .where((f) => f.lifecycle == FindingLifecycle.open || f.lifecycle == FindingLifecycle.deferred)
        .toList();

    return LayoutBuilder(
      builder: (context, constraints) {
        final isNarrow = constraints.maxWidth < 950;

        return SingleChildScrollView(
          padding: const EdgeInsets.all(32),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header
              Center(
                child: Column(
                  children: [
                    Text(
                      'LEAVE THE WORK. KEEP THE CONTEXT.',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        letterSpacing: 1.2,
                        color: tokens.secondaryText,
                      ),
                    ),
                    const SizedBox(height: 8),
                    Text(
                      'A good place to stop.',
                      style: TextStyle(fontSize: 32, fontWeight: FontWeight.bold, color: tokens.primaryText),
                    ),
                    const SizedBox(height: 6),
                    Text(
                      'You made progress. Here’s what you can leave here, and what tomorrow needs.',
                      style: TextStyle(fontSize: 15, color: tokens.secondaryText),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 32),

              // Two-column grid
              isNarrow
                  ? Column(
                      children: [
                        _buildLeftColumn(tokens, looseEnds),
                        const SizedBox(height: 24),
                        _buildRightColumn(tokens),
                      ],
                    )
                  : Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(flex: 6, child: _buildLeftColumn(tokens, looseEnds)),
                        const SizedBox(width: 24),
                        Expanded(flex: 5, child: _buildRightColumn(tokens)),
                      ],
                    ),
              const SizedBox(height: 32),

              // Bottom Actions
              Wrap(
                alignment: WrapAlignment.spaceBetween,
                runSpacing: 12,
                crossAxisAlignment: WrapCrossAlignment.center,
                children: [
                  Text(
                    'Your note lives locally in this session until you save or copy it.',
                    style: TextStyle(fontSize: 13, color: tokens.secondaryText),
                  ),
                  Wrap(
                    spacing: 12,
                    runSpacing: 8,
                    children: [
                      OutlinedButton(
                        style: OutlinedButton.styleFrom(
                          foregroundColor: tokens.secondaryText,
                          side: BorderSide(color: tokens.dividerLine),
                          padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        onPressed: widget.onBackToSession,
                        child: const Text('Back to session'),
                      ),
                      ElevatedButton.icon(
                        style: ElevatedButton.styleFrom(
                          backgroundColor: widget.isEnded ? tokens.softBrandSurface : tokens.brandAction,
                          foregroundColor: widget.isEnded ? tokens.brandAction : tokens.brandActionInk,
                          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                        ),
                        icon: Icon(widget.isEnded ? Icons.check_circle_outline : Icons.laptop_chromebook, size: 18),
                        label: Text(
                          widget.isEnded ? 'Session closed' : 'Leave it here',
                          style: const TextStyle(fontWeight: FontWeight.bold),
                        ),
                        onPressed: widget.isEnded ? null : widget.onFinalizeSession,
                      ),
                    ],
                  ),
                ],
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildLeftColumn(SteadyDevThemeTokens tokens, List<FindingItem> looseEnds) {
    return Column(
      children: [
        // What you can leave here
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: tokens.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: tokens.dividerLine),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.check_circle_outline, color: tokens.brandAction, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'What you can leave here',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: tokens.primaryText),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                '• Auth checks passing and verified in local receipts.\n• Tracked changes safely staged in working snapshot.',
                style: TextStyle(fontSize: 14, color: tokens.secondaryText, height: 1.5),
              ),
              const SizedBox(height: 12),
              Text(
                'Evidence is scoped to these checks—not a claim that the whole feature is finished.',
                style: TextStyle(fontSize: 12, color: tokens.secondaryText, fontStyle: FontStyle.italic),
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        // Loose ends
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: tokens.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: tokens.dividerLine),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(Icons.info_outline, color: tokens.badgeUnverifiedText, size: 20),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Loose ends, not failures',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: tokens.primaryText),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              if (looseEnds.isEmpty)
                Text(
                  'No open or deferred findings. That is not a guarantee that the project is complete.',
                  style: TextStyle(fontSize: 14, color: tokens.secondaryText),
                )
              else
                ...looseEnds.map((f) {
                  return Padding(
                    padding: const EdgeInsets.only(bottom: 14),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            Expanded(
                              child: Text(
                                f.title,
                                overflow: TextOverflow.ellipsis,
                                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: tokens.primaryText),
                              ),
                            ),
                            if (f.lifecycle == FindingLifecycle.deferred) ...[
                              const SizedBox(width: 8),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                decoration: BoxDecoration(
                                  color: tokens.subtleSurface,
                                  borderRadius: BorderRadius.circular(4),
                                ),
                                child: Text('Deferred',
                                    style: TextStyle(fontSize: 11, color: tokens.secondaryText)),
                              ),
                            ],
                          ],
                        ),
                        const SizedBox(height: 4),
                        Text(f.description, style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                        TextButton(
                          style: TextButton.styleFrom(
                            foregroundColor: tokens.brandAction,
                            padding: EdgeInsets.zero,
                          ),
                          onPressed: () => EvidenceDialog.show(context, f),
                          child: const Text('See why ->', style: TextStyle(fontSize: 12)),
                        ),
                      ],
                    ),
                  );
                }),
            ],
          ),
        ),
      ],
    );
  }

  Widget _buildRightColumn(SteadyDevThemeTokens tokens) {
    return Column(
      children: [
        // Tomorrow restart note card
        Container(
          padding: const EdgeInsets.all(24),
          decoration: BoxDecoration(
            color: tokens.softBrandSurface,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: tokens.brandOutline),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'A GIFT TO TOMORROW YOU',
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.1,
                  color: tokens.brandAction,
                ),
              ),
              const SizedBox(height: 8),
              Row(
                children: [
                  Icon(Icons.arrow_forward, size: 20, color: tokens.brandAction),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'Start here, not from scratch.',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: tokens.primaryText),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(
                'Edit the handoff so it sounds like you.',
                style: TextStyle(fontSize: 13, color: tokens.secondaryText),
              ),
              const SizedBox(height: 14),
              TextFormField(
                controller: _noteController,
                maxLines: 5,
                decoration: InputDecoration(
                  filled: true,
                  fillColor: tokens.panel,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(color: tokens.inputBoundary),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(color: tokens.brandAction, width: 2),
                  ),
                ),
                onChanged: (_) => _noteEdited = true,
              ),
              const SizedBox(height: 12),
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: tokens.panel,
                  foregroundColor: tokens.primaryText,
                  elevation: 0,
                  side: BorderSide(color: tokens.dividerLine),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                ),
                icon: Icon(_copied ? Icons.check : Icons.copy, size: 16),
                label: Text(_copied ? 'Copied' : 'Copy restart note'),
                onPressed: _copyNote,
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        // Stopping is not completing card
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: tokens.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: tokens.dividerLine),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Stopping is not completing.',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
              ),
              const SizedBox(height: 8),
              Text(
                'You can leave with open questions. Nothing is marked finished, committed, or sent to anyone.',
                style: TextStyle(fontSize: 13, color: tokens.secondaryText, height: 1.4),
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Icon(Icons.shield_outlined, size: 16, color: tokens.secondaryText),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(
                      'Local session only · no files committed or sent',
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: tokens.secondaryText),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ],
    );
  }
}
