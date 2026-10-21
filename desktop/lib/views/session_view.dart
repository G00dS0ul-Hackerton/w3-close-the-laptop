import 'package:flutter/material.dart';

import '../dialogs/evidence_dialog.dart';
import '../dialogs/intention_dialog.dart';
import '../dialogs/reason_dialog.dart';
import '../models/session_models.dart';
import '../theme/tokens.dart';

class SessionView extends StatelessWidget {
  final String repoName;
  final String intention;
  final List<String> criteria;
  final List<FindingItem> findings;
  final bool isReviewing;
  final bool isPaused;
  final bool isEnded;
  final String quietStatus;
  final VoidCallback onTriggerCheckpoint;
  final VoidCallback onTogglePause;
  final VoidCallback onNavigateToClosing;
  final ValueChanged<String> onUpdateIntention;
  final Function(FindingItem finding, FindingLifecycle status, String? reason) onUpdateFindingStatus;

  const SessionView({
    super.key,
    required this.repoName,
    required this.intention,
    required this.criteria,
    required this.findings,
    required this.isReviewing,
    required this.isPaused,
    required this.isEnded,
    required this.quietStatus,
    required this.onTriggerCheckpoint,
    required this.onTogglePause,
    required this.onNavigateToClosing,
    required this.onUpdateIntention,
    required this.onUpdateFindingStatus,
  });

  Widget _buildBadge(BuildContext context, FindingItem f) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;
    Color bg;
    Color fg;
    IconData icon;
    String label;

    switch (f.type) {
      case FindingType.confirmed:
        bg = tokens.badgeConfirmedBg;
        fg = tokens.badgeConfirmedText;
        icon = Icons.check_circle_outline;
        label = 'Confirmed';
        break;
      case FindingType.unverified:
        bg = tokens.badgeUnverifiedBg;
        fg = tokens.badgeUnverifiedText;
        icon = Icons.info_outline;
        label = 'Unverified';
        break;
      case FindingType.needsJudgment:
        bg = tokens.badgeJudgmentBg;
        fg = tokens.badgeJudgmentText;
        icon = Icons.help_outline;
        label = 'Needs your judgment';
        break;
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(color: bg, borderRadius: BorderRadius.circular(6)),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: fg),
          const SizedBox(width: 4),
          Text(label, style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: fg)),
        ],
      ),
    );
  }

  Widget _buildFindingCard(BuildContext context, FindingItem f) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;

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
              _buildBadge(context, f),
              if (f.lifecycle != FindingLifecycle.open)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: tokens.subtleSurface,
                    borderRadius: BorderRadius.circular(4),
                  ),
                  child: Text(
                    f.lifecycle.name.toUpperCase(),
                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: tokens.secondaryText),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            f.title,
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
          ),
          const SizedBox(height: 6),
          Text(
            f.description,
            style: TextStyle(fontSize: 14, color: tokens.secondaryText, height: 1.4),
          ),
          if (f.reason != null && f.reason!.isNotEmpty) ...[
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.only(left: 10),
              decoration: BoxDecoration(
                border: Border(left: BorderSide(color: tokens.dividerLine, width: 2)),
              ),
              child: Text(
                f.reason!,
                style: TextStyle(fontSize: 13, color: tokens.secondaryText, fontStyle: FontStyle.italic),
              ),
            ),
          ],
          const SizedBox(height: 14),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: TextButton.icon(
                  style: TextButton.styleFrom(
                    foregroundColor: tokens.brandAction,
                    padding: EdgeInsets.zero,
                    minimumSize: const Size(44, 44),
                  ),
                  icon: const Icon(Icons.arrow_forward, size: 16),
                  label: const Text('View evidence', overflow: TextOverflow.ellipsis),
                  onPressed: () => EvidenceDialog.show(context, f),
                ),
              ),
              Row(
                children: [
                  IconButton(
                    icon: const Icon(Icons.check, size: 18),
                    tooltip: 'Mark as resolved',
                    onPressed: () async {
                      final reason = await ReasonDialog.show(
                        context,
                        finding: f,
                        targetStatus: FindingLifecycle.resolved,
                      );
                      if (reason != null) {
                        onUpdateFindingStatus(f, FindingLifecycle.resolved, reason);
                      }
                    },
                  ),
                  IconButton(
                    icon: const Icon(Icons.access_time, size: 18),
                    tooltip: 'Leave for later',
                    onPressed: () async {
                      final reason = await ReasonDialog.show(
                        context,
                        finding: f,
                        targetStatus: FindingLifecycle.deferred,
                      );
                      if (reason != null) {
                        onUpdateFindingStatus(f, FindingLifecycle.deferred, reason);
                      }
                    },
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, size: 18),
                    tooltip: 'Dismiss finding',
                    onPressed: () async {
                      final reason = await ReasonDialog.show(
                        context,
                        finding: f,
                        targetStatus: FindingLifecycle.dismissed,
                      );
                      if (reason != null) {
                        onUpdateFindingStatus(f, FindingLifecycle.dismissed, reason);
                      }
                    },
                  ),
                ],
              ),
            ],
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;
    final openFindings = findings.where((f) => f.lifecycle == FindingLifecycle.open).toList();

    return LayoutBuilder(
      builder: (context, constraints) {
        final isNarrow = constraints.maxWidth < 950;

        return SingleChildScrollView(
          padding: const EdgeInsets.all(28),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Intro header
              Wrap(
                alignment: WrapAlignment.spaceBetween,
                runSpacing: 16,
                crossAxisAlignment: WrapCrossAlignment.start,
                children: [
                  ConstrainedBox(
                    constraints: const BoxConstraints(maxWidth: 600),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'A QUIETER WAY TO WORK',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.bold,
                            letterSpacing: 1.2,
                            color: tokens.secondaryText,
                          ),
                        ),
                        const SizedBox(height: 6),
                        Text(
                          'Stay in flow. Keep the thread.',
                          style: TextStyle(
                            fontSize: 28,
                            fontWeight: FontWeight.bold,
                            color: tokens.primaryText,
                          ),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          'Loose ends, held gently until you’re ready to stop.',
                          style: TextStyle(fontSize: 15, color: tokens.secondaryText),
                        ),
                      ],
                    ),
                  ),
                  ElevatedButton.icon(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: tokens.brandAction,
                      foregroundColor: tokens.brandActionInk,
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    icon: const Icon(Icons.nightlight_round, size: 18),
                    label: const Text('I’m stopping', style: TextStyle(fontWeight: FontWeight.bold)),
                    onPressed: onNavigateToClosing,
                  ),
                ],
              ),
              const SizedBox(height: 24),

              // Layout grid
              isNarrow
                  ? Column(
                      children: [
                        _buildLeftColumn(context, tokens, openFindings),
                        const SizedBox(height: 24),
                        _buildRightColumn(context, tokens),
                      ],
                    )
                  : Row(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Expanded(flex: 7, child: _buildLeftColumn(context, tokens, openFindings)),
                        const SizedBox(width: 24),
                        Expanded(flex: 4, child: _buildRightColumn(context, tokens)),
                      ],
                    ),
            ],
          ),
        );
      },
    );
  }

  Widget _buildLeftColumn(BuildContext context, SteadyDevThemeTokens tokens, List<FindingItem> openFindings) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // Intention Card
        Container(
          padding: const EdgeInsets.all(22),
          decoration: BoxDecoration(
            color: tokens.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: tokens.dividerLine),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'TODAY’S INTENTION',
                    style: TextStyle(
                      fontSize: 11,
                      fontWeight: FontWeight.bold,
                      letterSpacing: 1.1,
                      color: tokens.secondaryText,
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.edit_outlined, size: 18),
                    tooltip: 'Edit session intention',
                    onPressed: () async {
                      final updated = await IntentionDialog.show(context, intention);
                      if (updated != null) {
                        onUpdateIntention(updated);
                      }
                    },
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                intention,
                style: TextStyle(
                  fontSize: 18,
                  fontWeight: FontWeight.bold,
                  color: tokens.primaryText,
                  height: 1.3,
                ),
              ),
              const SizedBox(height: 14),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: criteria
                    .map(
                      (c) => Container(
                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                        decoration: BoxDecoration(
                          color: tokens.subtleSurface,
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: tokens.dividerLine),
                        ),
                        child: Text(c, style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                      ),
                    )
                    .toList(),
              ),
            ],
          ),
        ),
        const SizedBox(height: 24),

        // Section Title
        Wrap(
          alignment: WrapAlignment.spaceBetween,
          runSpacing: 6,
          crossAxisAlignment: WrapCrossAlignment.center,
          children: [
            Wrap(
              spacing: 8,
              runSpacing: 4,
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                Text(
                  'Worth a second look',
                  style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: tokens.primaryText),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: tokens.subtleSurface,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Text(
                    '${openFindings.length} open',
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: tokens.secondaryText),
                  ),
                ),
              ],
            ),
            Text(
              'Not a to-do avalanche',
              style: TextStyle(fontSize: 13, color: tokens.secondaryText),
            ),
          ],
        ),
        const SizedBox(height: 14),

        // Findings List or Empty State
        if (openFindings.isEmpty)
          Container(
            padding: const EdgeInsets.all(32),
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
                  'No open findings.',
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
                ),
                const SizedBox(height: 4),
                Text(
                  'Deferred items remain in your closing card.',
                  style: TextStyle(fontSize: 13, color: tokens.secondaryText),
                ),
              ],
            ),
          )
        else
          ...openFindings.map((f) => _buildFindingCard(context, f)),

        const SizedBox(height: 14),
        Row(
          children: [
            Icon(Icons.shield_outlined, size: 16, color: tokens.secondaryText),
            const SizedBox(width: 6),
            Expanded(
              child: Text(
                'Live findings from local reviewer. Nothing here modifies your code.',
                style: TextStyle(fontSize: 12, color: tokens.secondaryText),
              ),
            ),
          ],
        ),
      ],
    );
  }

  Widget _buildRightColumn(BuildContext context, SteadyDevThemeTokens tokens) {
    return Column(
      children: [
        // Quiet Review Card
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
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: tokens.softBrandSurface,
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(Icons.layers_outlined, color: tokens.brandAction, size: 20),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'Quiet review',
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
                        ),
                        Text(
                          isReviewing
                              ? 'Reviewing snapshot...'
                              : isPaused
                                  ? 'Review paused'
                                  : quietStatus,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(fontSize: 12, color: tokens.secondaryText),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 14),
              Text(
                'Spaced checkpoints, not keystroke tracking. Local CPU execution.',
                style: TextStyle(fontSize: 13, color: tokens.secondaryText),
              ),
              const SizedBox(height: 18),
              Divider(height: 1, color: tokens.dividerLine),
              const SizedBox(height: 14),
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Flexible(
                    child: TextButton.icon(
                      style: TextButton.styleFrom(
                        foregroundColor: tokens.brandAction,
                        minimumSize: const Size(44, 44),
                      ),
                      icon: isReviewing
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.refresh, size: 16),
                      label: Text(
                        isReviewing ? 'Reviewing...' : 'Try a checkpoint',
                        overflow: TextOverflow.ellipsis,
                      ),
                      onPressed: isReviewing ? null : onTriggerCheckpoint,
                    ),
                  ),
                  IconButton(
                    icon: Icon(isPaused ? Icons.play_arrow : Icons.pause, size: 20),
                    tooltip: isPaused ? 'Resume quiet review' : 'Pause quiet review',
                    onPressed: onTogglePause,
                  ),
                ],
              ),
            ],
          ),
        ),
        const SizedBox(height: 20),

        // What Has Evidence Card
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
                'What has evidence',
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: tokens.primaryText),
              ),
              const SizedBox(height: 14),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(color: tokens.badgeConfirmedBg, shape: BoxShape.circle),
                    child: Icon(Icons.check, size: 14, color: tokens.badgeConfirmedText),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Auth checks',
                            style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: tokens.primaryText)),
                        Text('6 checks passed with assertions recorded.',
                            style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Container(
                    padding: const EdgeInsets.all(6),
                    decoration: BoxDecoration(color: tokens.badgeConfirmedBg, shape: BoxShape.circle),
                    child: Icon(Icons.check, size: 14, color: tokens.badgeConfirmedText),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Error-state check',
                            style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: tokens.primaryText)),
                        Text('Previously flagged gap now retired.',
                            style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                      ],
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
