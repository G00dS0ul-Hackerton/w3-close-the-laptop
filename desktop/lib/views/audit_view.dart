import 'package:flutter/material.dart';

import '../dialogs/evidence_dialog.dart';
import '../models/session_models.dart';
import '../theme/tokens.dart';

class AuditView extends StatefulWidget {
  final List<FindingItem> findings;
  final Function(FindingItem finding, FindingLifecycle status, String? reason) onUpdateFindingStatus;

  const AuditView({
    super.key,
    required this.findings,
    required this.onUpdateFindingStatus,
  });

  @override
  State<AuditView> createState() => _AuditViewState();
}

class _AuditViewState extends State<AuditView> {
  String _activeFilter = 'open';

  List<FindingItem> get _filteredFindings {
    if (_activeFilter == 'all') return widget.findings;
    return widget.findings
        .where((f) => f.lifecycle.name.toLowerCase() == _activeFilter.toLowerCase())
        .toList();
  }

  Widget _buildLegendItem(IconData icon, Color color, String label) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 14, color: color),
        const SizedBox(width: 6),
        Text(label, style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w500)),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;
    final items = _filteredFindings;

    return LayoutBuilder(
      builder: (context, constraints) {
        final isNarrow = constraints.maxWidth < 950;

        return SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Intro
              Text(
                'EVIDENCE, NOT ASSUMPTIONS',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  letterSpacing: 1.2,
                  color: tokens.secondaryText,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                'A small, honest second look.',
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.bold, color: tokens.primaryText),
              ),
              const SizedBox(height: 4),
              Text(
                'Separate what’s known from what still needs your judgment.',
                style: TextStyle(fontSize: 15, color: tokens.secondaryText),
              ),
              const SizedBox(height: 18),

              // Legend
              Wrap(
                spacing: 18,
                runSpacing: 8,
                children: [
                  _buildLegendItem(Icons.check_circle_outline, tokens.badgeConfirmedText, 'Confirmed by evidence'),
                  _buildLegendItem(Icons.info_outline, tokens.badgeUnverifiedText, 'Unverified'),
                  _buildLegendItem(Icons.help_outline, tokens.badgeJudgmentText, 'Needs your judgment'),
                ],
              ),
              const SizedBox(height: 20),

              // Filter Toolbar
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: ['open', 'deferred', 'resolved', 'evidenceRetired', 'dismissed', 'all'].map((filter) {
                  final isSelected = _activeFilter == filter;
                  final label = filter == 'evidenceRetired'
                      ? 'Evidence-retired'
                      : filter == 'all'
                          ? 'All findings'
                          : filter[0].toUpperCase() + filter.substring(1);

                  return ChoiceChip(
                    label: Text(label),
                    selected: isSelected,
                    selectedColor: tokens.panel,
                    backgroundColor: tokens.subtleSurface,
                    labelStyle: TextStyle(
                      fontSize: 13,
                      fontWeight: isSelected ? FontWeight.bold : FontWeight.normal,
                      color: isSelected ? tokens.primaryText : tokens.secondaryText,
                    ),
                    side: BorderSide(
                      color: isSelected ? tokens.brandOutline : tokens.dividerLine,
                    ),
                    onSelected: (val) {
                      if (val) setState(() => _activeFilter = filter);
                    },
                  );
                }).toList(),
              ),
              const SizedBox(height: 24),

              // Content Grid
              isNarrow
                  ? Column(
                      children: [
                        _buildFindingsList(tokens, items),
                        const SizedBox(height: 24),
                        _buildAside(tokens),
                      ],
                    )
                  : Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(flex: 7, child: _buildFindingsList(tokens, items)),
                        const SizedBox(width: 24),
                        Expanded(flex: 4, child: _buildAside(tokens)),
                      ],
                    ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildFindingsList(SteadyDevThemeTokens tokens, List<FindingItem> items) {
    if (items.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(36),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: tokens.panel,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: tokens.dividerLine),
        ),
        child: Column(
          children: [
            Icon(Icons.check_circle, size: 36, color: tokens.brandAction),
            const SizedBox(height: 10),
            Text(
              'Nothing $_activeFilter here.',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
            ),
            const SizedBox(height: 4),
            Text(
              'Findings appear here when their status matches this filter.',
              style: TextStyle(fontSize: 13, color: tokens.secondaryText),
            ),
          ],
        ),
      );
    }

    return Column(
      children: items.map((f) {
        return Container(
          margin: const EdgeInsets.only(bottom: 14),
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: tokens.panel,
            borderRadius: BorderRadius.circular(10),
            border: Border.all(color: tokens.dividerLine),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    f.type == FindingType.confirmed
                        ? 'Confirmed'
                        : f.type == FindingType.unverified
                            ? 'Unverified'
                            : 'Needs judgment',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: tokens.brandAction),
                  ),
                  Wrap(
                    spacing: 6,
                    children: [
                      if (f.isStale)
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                          decoration: BoxDecoration(
                            color: tokens.softBrandSurface,
                            borderRadius: BorderRadius.circular(4),
                            border: Border.all(color: tokens.badgeUnverifiedText),
                          ),
                          child: Text(
                            'STALE LOCATOR',
                            style: TextStyle(
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                              color: tokens.badgeUnverifiedText,
                            ),
                          ),
                        ),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: f.lifecycle == FindingLifecycle.evidenceRetired
                              ? tokens.softBrandSurface
                              : tokens.subtleSurface,
                          borderRadius: BorderRadius.circular(4),
                          border: f.lifecycle == FindingLifecycle.evidenceRetired
                              ? Border.all(color: tokens.brandAction)
                              : null,
                        ),
                        child: Text(
                          f.lifecycle == FindingLifecycle.evidenceRetired
                              ? 'EVIDENCE-RETIRED'
                              : f.lifecycle == FindingLifecycle.resolved
                                  ? 'USER RESOLVED'
                                  : f.lifecycle.name.toUpperCase(),
                          style: TextStyle(
                            fontSize: 11,
                            fontWeight: FontWeight.bold,
                            color: f.lifecycle == FindingLifecycle.evidenceRetired
                                ? tokens.brandAction
                                : tokens.secondaryText,
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                f.title,
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
              ),
              const SizedBox(height: 4),
              Text(
                f.description,
                style: TextStyle(fontSize: 14, color: tokens.secondaryText),
              ),
              if (f.isStale && f.staleReason != null) ...[
                const SizedBox(height: 6),
                Text(
                  'Stale: ${f.staleReason}',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: tokens.badgeUnverifiedText,
                  ),
                ),
              ],
              if (f.reason != null && f.reason!.isNotEmpty) ...[
                const SizedBox(height: 8),
                Text(
                  'Context: ${f.reason}',
                  style: TextStyle(fontSize: 13, color: tokens.secondaryText, fontStyle: FontStyle.italic),
                ),
              ],
              const SizedBox(height: 12),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  TextButton.icon(
                    style: TextButton.styleFrom(foregroundColor: tokens.brandAction, padding: EdgeInsets.zero),
                    icon: const Icon(Icons.arrow_forward, size: 16),
                    label: const Text('View evidence'),
                    onPressed: () => EvidenceDialog.show(context, f),
                  ),
                  if (f.lifecycle != FindingLifecycle.open)
                    TextButton.icon(
                      style: TextButton.styleFrom(foregroundColor: tokens.secondaryText),
                      icon: const Icon(Icons.refresh, size: 16),
                      label: const Text('Reopen'),
                      onPressed: () => widget.onUpdateFindingStatus(f, FindingLifecycle.open, null),
                    ),
                ],
              ),
            ],
          ),
        );
      }).toList(),
    );
  }

  Widget _buildAside(SteadyDevThemeTokens tokens) {
    return Column(
      children: [
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
                'A finding is not a verdict.',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
              ),
              const SizedBox(height: 10),
              Text(
                '“No check recorded” doesn’t mean you forgot. You can add context, resolve it, or leave it for tomorrow.',
                style: TextStyle(fontSize: 13, color: tokens.secondaryText, height: 1.4),
              ),
            ],
          ),
        ),
      ],
    );
  }
}
