import 'dart:async';

import 'package:flutter/material.dart';

import '../models/session_models.dart';
import '../services/api_client.dart';
import '../theme/tokens.dart';
import 'telemetry_settings_dialog.dart';

class DiagnosticsDialog extends StatefulWidget {
  final SteadyDevApiClient? apiClient;
  final ReviewDiagnosticsData? initialData;

  const DiagnosticsDialog({
    super.key,
    this.apiClient,
    this.initialData,
  });

  static Future<void> show(
    BuildContext context, {
    SteadyDevApiClient? apiClient,
    ReviewDiagnosticsData? initialData,
  }) async {
    await showDialog(
      context: context,
      builder: (ctx) => DiagnosticsDialog(
        apiClient: apiClient,
        initialData: initialData,
      ),
    );
  }

  @override
  State<DiagnosticsDialog> createState() => _DiagnosticsDialogState();
}

class _DiagnosticsDialogState extends State<DiagnosticsDialog> {
  ReviewDiagnosticsData? _diagnostics;
  TelemetryConfigData? _telemetryConfig;
  bool _isLoading = false;
  bool _isPollingInFlight = false;
  String? _errorMessage;
  Timer? _pollTimer;

  @override
  void initState() {
    super.initState();
    _diagnostics = widget.initialData;
    _fetchDiagnostics();
    // Start 1s live polling for countdown and chunk progress
    if (widget.apiClient != null) {
      _pollTimer = Timer.periodic(const Duration(seconds: 1), (_) {
        _pollDiagnosticsSilent();
      });
    }
  }

  @override
  void dispose() {
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _fetchDiagnostics() async {
    if (widget.apiClient == null) return;
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final diagFuture = widget.apiClient!.getReviewDiagnostics();
      final telemFuture = widget.apiClient!.getTelemetryConfig();
      final diag = await diagFuture;
      final telem = await telemFuture;
      if (mounted) {
        setState(() {
          _diagnostics = diag ?? _diagnostics;
          _telemetryConfig = telem;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoading = false;
          _errorMessage = e.toString();
        });
      }
    }
  }

  /// Silent poll — no loading spinner, no error overwrite. Skips if another
  /// poll is already in-flight (prevents request pile-up per O-3).
  Future<void> _pollDiagnosticsSilent() async {
    if (widget.apiClient == null) return;
    if (_isPollingInFlight) return;
    _isPollingInFlight = true;
    try {
      final diagFuture = widget.apiClient!.getReviewDiagnostics();
      final telemFuture = widget.apiClient!.getTelemetryConfig();
      final diag = await diagFuture;
      final telem = await telemFuture;
      if (mounted) {
        setState(() {
          _diagnostics = diag ?? _diagnostics;
          _telemetryConfig = telem;
        });
      }
    } catch (_) {
      // Silent — do not overwrite existing data on transient errors
    } finally {
      _isPollingInFlight = false;
    }
  }

  String _formatModelTag(String raw) {
    if (raw.contains('gemma')) return 'Gemma 3 4B';
    if (raw.contains('qwen')) return 'Qwen 2.5 Coder 3B';
    if (raw.contains('baseline')) return 'Baseline Checklist';
    return raw;
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ??
        SteadyDevThemeTokens.light;

    return AlertDialog(
      backgroundColor: tokens.panel,
      titlePadding: const EdgeInsets.fromLTRB(20, 20, 20, 0),
      contentPadding: const EdgeInsets.fromLTRB(20, 16, 20, 16),
      title: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Expanded(
            child: Row(
              children: [
                Icon(Icons.analytics_outlined, color: tokens.brandAction, size: 22),
                const SizedBox(width: 10),
                Flexible(
                  child: Text(
                    'Review Diagnostics',
                    style: TextStyle(
                      color: tokens.primaryText,
                      fontSize: 18,
                      fontWeight: FontWeight.bold,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
              ],
            ),
          ),
          Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              if (widget.apiClient != null)
                IconButton(
                  icon: const Icon(Icons.settings_outlined, size: 20),
                  tooltip: 'Sentry Telemetry Settings',
                  onPressed: () async {
                    await TelemetrySettingsDialog.show(
                      context,
                      apiClient: widget.apiClient!,
                      initialConfig: _telemetryConfig,
                    );
                    _fetchDiagnostics();
                  },
                ),
              IconButton(
                icon: const Icon(Icons.refresh, size: 20),
                tooltip: 'Refresh diagnostics',
                onPressed: _isLoading ? null : _fetchDiagnostics,
              ),
            ],
          ),
        ],
      ),
      content: SizedBox(
        width: 640,
        child: ConstrainedBox(
          constraints: BoxConstraints(
            maxHeight: MediaQuery.of(context).size.height * 0.75,
          ),
          child: _isLoading && _diagnostics == null
              ? const SizedBox(
                  height: 200,
                  child: Center(child: CircularProgressIndicator()),
                )
              : _errorMessage != null && _diagnostics == null
                  ? SizedBox(
                      height: 150,
                      child: Center(
                        child: Text(
                          _errorMessage!,
                          style: TextStyle(color: tokens.badgeJudgmentText),
                        ),
                      ),
                    )
                  : SingleChildScrollView(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          _buildStatusCard(context, tokens),
                          const SizedBox(height: 16),
                          _buildTimingBreakdown(tokens),
                          const SizedBox(height: 16),
                          _buildOperationalSummary(context, tokens),
                          const SizedBox(height: 16),
                          _buildChunkMatrix(context, tokens),
                          const SizedBox(height: 16),
                          _buildTelemetryExportCard(context, tokens),
                          const SizedBox(height: 16),
                          _buildOfflineFooter(context, tokens),
                        ],
                      ),
                    ),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Close'),
        ),
      ],
    );
  }

  Widget _buildStatusCard(BuildContext context, SteadyDevThemeTokens tokens) {
    final diag = _diagnostics;
    final phase = diag?.phase ?? 'idle';
    final elapsedS = (diag?.elapsedMs ?? 0.0) / 1000.0;
    final deadlineS = diag?.deadlineSeconds;
    final isUnlimited = deadlineS == null;
    final deadlineExceeded = diag?.deadlineExceeded ?? false;

    // Progress fraction: 0..1 for bounded, null for indeterminate (Unlimited while reviewing)
    final double? progressFraction;
    if (isUnlimited) {
      progressFraction = (diag?.isReviewing == true) ? null : 1.0;
    } else {
      progressFraction = (elapsedS / deadlineS).clamp(0.0, 1.0);
    }

    // Labels
    final String budgetLabel;
    final String remainLabel;
    if (isUnlimited) {
      budgetLabel =
          'Workflow Budget (${elapsedS.toStringAsFixed(1)}s / Unlimited)';
      remainLabel = 'No timeout limit';
    } else {
      budgetLabel =
          'Workflow Deadline (${elapsedS.toStringAsFixed(1)}s / ${deadlineS.toStringAsFixed(0)}s)';
      remainLabel = deadlineExceeded
          ? 'EXCEEDED'
          : '${(deadlineS - elapsedS).clamp(0.0, deadlineS).toStringAsFixed(1)}s remaining';
    }

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: tokens.subtleSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: tokens.dividerLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Wrap(
                  spacing: 8,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      'Lifecycle Phase:',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: tokens.secondaryText,
                      ),
                    ),
                    Container(
                      padding:
                          const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                      decoration: BoxDecoration(
                        color: phase == 'completed'
                            ? tokens.badgeConfirmedBg
                            : (deadlineExceeded ||
                                    phase == 'failed' ||
                                    phase == 'timed_out'
                                ? tokens.badgeJudgmentBg
                                : tokens.brandAction.withValues(alpha: 0.15)),
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        phase.toUpperCase(),
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          color: phase == 'completed'
                              ? tokens.badgeConfirmedText
                              : (deadlineExceeded ||
                                      phase == 'failed' ||
                                      phase == 'timed_out'
                                  ? tokens.badgeJudgmentText
                                  : tokens.brandAction),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (diag?.reviewId != null && diag!.reviewId != 'idle')
                Flexible(
                  child: Text(
                    'ID: ${diag.reviewId}',
                    style:
                        TextStyle(fontSize: 11, color: tokens.secondaryText),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
          const SizedBox(height: 12),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Text(
                  budgetLabel,
                  style: TextStyle(fontSize: 12, color: tokens.primaryText),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              Text(
                remainLabel,
                style: TextStyle(
                  fontSize: 11,
                  fontWeight: FontWeight.bold,
                  color: deadlineExceeded
                      ? tokens.badgeJudgmentText
                      : tokens.secondaryText,
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          ClipRRect(
            borderRadius: BorderRadius.circular(3),
            child: LinearProgressIndicator(
              value: progressFraction,
              minHeight: 6,
              backgroundColor: tokens.dividerLine,
              valueColor: AlwaysStoppedAnimation<Color>(
                deadlineExceeded
                    ? tokens.badgeJudgmentText
                    : tokens.brandAction,
              ),
            ),
          ),
          if (diag?.error != null) ...[
            const SizedBox(height: 8),
            Text(
              'Notice: ${diag!.error!}',
              style: TextStyle(
                  fontSize: 11,
                  color: tokens.badgeJudgmentText,
                  fontStyle: FontStyle.italic),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildChunkMatrix(BuildContext context, SteadyDevThemeTokens tokens) {
    final chunks = _diagnostics?.chunkDiagnostics ?? [];
    if (chunks.isEmpty) {
      return Container(
        padding: const EdgeInsets.all(16),
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: tokens.subtleSurface,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: tokens.dividerLine),
        ),
        child: Text(
          'No chunk telemetry recorded for this review yet.',
          style: TextStyle(fontSize: 12, color: tokens.secondaryText),
        ),
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Chunk Coverage & Model Attempts (${chunks.length} chunks)',
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
            color: tokens.primaryText,
          ),
        ),
        const SizedBox(height: 8),
        ...chunks.map((cp) => _buildChunkCard(context, cp, tokens)),
      ],
    );
  }

  Widget _buildChunkCard(
    BuildContext context,
    ChunkProvenanceData cp,
    SteadyDevThemeTokens tokens,
  ) {
    final isBaseline = cp.resolvedEngine.contains('baseline');

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: tokens.subtleSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: tokens.dividerLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Text(
                      'Chunk ${cp.chunkIndex} of ${cp.totalChunks}',
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        fontSize: 13,
                        color: tokens.primaryText,
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: isBaseline ? tokens.badgeJudgmentBg : tokens.badgeConfirmedBg,
                        borderRadius: BorderRadius.circular(4),
                      ),
                      child: Text(
                        isBaseline ? 'Baseline Floor' : _formatModelTag(cp.resolvedEngine),
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                          color: isBaseline ? tokens.badgeJudgmentText : tokens.badgeConfirmedText,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              Text(
                '${cp.findingsCount} findings',
                style: TextStyle(fontSize: 11, color: tokens.secondaryText),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Text(
            'Files: ${cp.filePaths.join(', ')}',
            style: TextStyle(fontSize: 11, color: tokens.secondaryText),
          ),
          if (cp.fallbackReason != null) ...[
            const SizedBox(height: 4),
            Text(
              'Fallback Trigger: ${cp.fallbackReason}',
              style: TextStyle(
                fontSize: 11,
                fontStyle: FontStyle.italic,
                color: tokens.badgeJudgmentText,
              ),
            ),
          ],
          if (cp.attempts.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text(
              'Model Invocations:',
              style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: tokens.secondaryText),
            ),
            const SizedBox(height: 4),
            ...cp.attempts.map((att) => Padding(
                  padding: const EdgeInsets.only(left: 6, bottom: 2),
                  child: Row(
                    children: [
                      Icon(
                        att.outcome == 'success' ? Icons.check_circle_outline : Icons.error_outline,
                        size: 13,
                        color: att.outcome == 'success' ? tokens.brandAction : tokens.badgeJudgmentText,
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: Text(
                          '${att.model}: ${att.outcome} · ${(att.durationMs / 1000.0).toStringAsFixed(1)}s · ${att.inputTokens ?? 0} in / ${att.outputTokens ?? 0} out${att.doneReason != null ? ' · reason=${att.doneReason}' : ''}',
                          style: TextStyle(fontSize: 11, color: tokens.secondaryText),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                    ],
                  ),
                )),
          ],
        ],
      ),
    );
  }

  Widget _buildTelemetryExportCard(BuildContext context, SteadyDevThemeTokens tokens) {
    final telem = _telemetryConfig;
    final state = telem?.exportState ?? 'disabled';
    final isEnabled = telem?.enabled == true;
    final isDelivered = telem?.verifiedDelivery == true;
    final traceId = telem?.lastTraceId;
    final traceUrl = telem?.traceUrl;
    final isDisabled = state == 'disabled';

    Color badgeColor;
    String badgeText;
    switch (state) {
      case 'verified_delivered':
        badgeColor = tokens.badgeConfirmedText;
        badgeText = 'VERIFIED DELIVERED';
        break;
      case 'local_only':
        badgeColor = tokens.brandAction;
        badgeText = 'ENABLED (ACTIVE)';
        break;
      case 'staged_local':
      case 'flushing':
        badgeColor = tokens.badgeUnverifiedText;
        badgeText = isEnabled
            ? 'IN-FLIGHT (BUFFERING TO SENTRY)'
            : 'STAGED LOCAL';
        break;
      case 'delivery_failed':
        badgeColor = tokens.badgeJudgmentText;
        badgeText = 'DELIVERY FAILED';
        break;
      default:
        badgeColor = tokens.secondaryText;
        badgeText = 'DISABLED (OFFLINE ONLY)';
    }

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: tokens.panel,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: tokens.dividerLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Expanded(
                child: Wrap(
                  spacing: 6,
                  runSpacing: 4,
                  crossAxisAlignment: WrapCrossAlignment.center,
                  children: [
                    Icon(Icons.cloud_sync_outlined, size: 16, color: tokens.brandAction),
                    Text(
                      'Sentry Telemetry:',
                      style: TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.bold,
                        color: tokens.primaryText,
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: badgeColor.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(4),
                        border: Border.all(color: badgeColor),
                      ),
                      child: Text(
                        badgeText,
                        style: TextStyle(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: badgeColor,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              if (widget.apiClient != null)
                TextButton(
                  onPressed: () async {
                    await TelemetrySettingsDialog.show(
                      context,
                      apiClient: widget.apiClient!,
                      initialConfig: _telemetryConfig,
                    );
                    _fetchDiagnostics();
                  },
                  style: TextButton.styleFrom(
                    visualDensity: VisualDensity.compact,
                    padding: const EdgeInsets.symmetric(horizontal: 8),
                  ),
                  child: Text(
                    'Configure',
                    style: TextStyle(fontSize: 11, color: tokens.brandAction),
                  ),
                ),
            ],
          ),
          // Only show Trace ID when telemetry is not disabled
          if (!isDisabled && traceId != null && traceId.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              'Trace ID: $traceId',
              style: TextStyle(
                fontSize: 11,
                fontFamily: 'monospace',
                color: tokens.secondaryText,
              ),
            ),
          ],
          if (isDelivered && traceUrl != null && traceUrl.isNotEmpty) ...[
            const SizedBox(height: 4),
            SelectableText(
              'Trace URL: $traceUrl',
              style: TextStyle(
                fontSize: 11,
                color: tokens.brandAction,
                decoration: TextDecoration.underline,
              ),
            ),
          ],
        ],
      ),
    );
  }

  Widget _buildTimingBreakdown(SteadyDevThemeTokens tokens) {
    final client = widget.apiClient;
    final uiDuration = client?.lastUiDurationMs != null
        ? '${(client!.lastUiDurationMs! / 1000).toStringAsFixed(2)}s'
        : 'N/A';
    final apiLatency = client?.lastApiLatencyMs != null
        ? '${client!.lastApiLatencyMs!.toStringAsFixed(0)}ms'
        : 'N/A';
    final backendDuration = client?.lastBackendDurationMs != null
        ? '${(client!.lastBackendDurationMs! / 1000).toStringAsFixed(2)}s'
        : (_diagnostics?.elapsedMs != null
            ? '${(_diagnostics!.elapsedMs / 1000).toStringAsFixed(2)}s'
            : 'N/A');
    final runId = client?.lastRunId ?? 'N/A';

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: tokens.subtleSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: tokens.dividerLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'Cross-Process Timing & Correlation',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: tokens.primaryText,
                ),
              ),
              Flexible(
                child: Text(
                  'Run ID: $runId',
                  overflow: TextOverflow.ellipsis,
                  style: TextStyle(
                    fontSize: 10,
                    fontFamily: 'monospace',
                    color: tokens.secondaryText,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              Expanded(
                child: _buildMetricItem(
                  'Client UI Duration',
                  uiDuration,
                  tokens,
                ),
              ),
              Expanded(
                child: _buildMetricItem(
                  'HTTP API Latency',
                  apiLatency,
                  tokens,
                ),
              ),
              Expanded(
                child: _buildMetricItem(
                  'Backend Review',
                  backendDuration,
                  tokens,
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildOperationalSummary(
      BuildContext context, SteadyDevThemeTokens tokens) {
    final diag = _diagnostics;
    final totalChunks = diag?.totalChunks ?? 0;
    final completedChunks = diag?.chunkDiagnostics.length ?? 0;
    final deadlineS = diag?.deadlineSeconds;
    final elapsedS = (diag?.elapsedMs ?? 0.0) / 1000.0;
    final marginLabel = deadlineS != null
        ? '${(deadlineS - elapsedS).clamp(0.0, double.infinity).toStringAsFixed(1)}s margin'
        : 'Unlimited';
    final coverageLabel = totalChunks > 0
        ? '$completedChunks / $totalChunks chunks (${((completedChunks / totalChunks) * 100).toInt()}%)'
        : '0 chunks';
    final phaseLabel = (diag?.phase ?? 'idle').toUpperCase();

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: tokens.subtleSurface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: tokens.dividerLine),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Flexible(
                child: Text(
                  'Pipeline Latency & Reliability Telemetry',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.bold,
                    color: tokens.primaryText,
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: tokens.panel,
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: tokens.dividerLine),
                ),
                child: Text(
                  'OPERATIONAL VIEW',
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    color: tokens.secondaryText,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Row(
            children: [
              Expanded(
                child: _buildMetricItem(
                  'Pipeline Phase',
                  'State: $phaseLabel',
                  tokens,
                ),
              ),
              Expanded(
                child: _buildMetricItem(
                  'Timeout Margin',
                  marginLabel,
                  tokens,
                ),
              ),
              Expanded(
                child: _buildMetricItem(
                  'Chunk Coverage',
                  coverageLabel,
                  tokens,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: tokens.panel,
              borderRadius: BorderRadius.circular(6),
              border: Border.all(color: tokens.dividerLine),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(
                  Icons.info_outline,
                  size: 14,
                  color: tokens.secondaryText,
                ),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(
                    'These metrics measure system performance and reliability boundaries. They do NOT evaluate model semantic accuracy, code correctness, or guarantee bug detection.',
                    style: TextStyle(
                      fontSize: 10,
                      color: tokens.secondaryText,
                      height: 1.3,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMetricItem(String label, String value, SteadyDevThemeTokens tokens) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          label,
          style: TextStyle(fontSize: 10, color: tokens.secondaryText),
        ),
        const SizedBox(height: 2),
        Text(
          value,
          style: TextStyle(
            fontSize: 13,
            fontWeight: FontWeight.bold,
            color: tokens.primaryText,
          ),
        ),
      ],
    );
  }

  Widget _buildOfflineFooter(BuildContext context, SteadyDevThemeTokens tokens) {
    final isSentryActive = _telemetryConfig?.enabled == true;
    final label = isSentryActive
        ? 'Local Review Execution · Sanitized Sentry Telemetry Active · Zero Source Egress'
        : '100% Local Diagnostics · Zero Network Egress · Independent of Sentry';

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: tokens.panel,
        borderRadius: BorderRadius.circular(6),
        border: Border.all(color: tokens.dividerLine),
      ),
      child: Row(
        children: [
          Icon(Icons.shield_outlined,
              size: 16,
              color: isSentryActive ? tokens.brandAction : tokens.secondaryText),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              label,
              style: TextStyle(
                fontSize: 11,
                color: isSentryActive ? tokens.primaryText : tokens.secondaryText,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
