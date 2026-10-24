import 'package:flutter/material.dart';

import '../models/session_models.dart';
import '../services/api_client.dart';
import '../theme/tokens.dart';

class TelemetrySettingsDialog extends StatefulWidget {
  final SteadyDevApiClient apiClient;
  final TelemetryConfigData? initialConfig;

  const TelemetrySettingsDialog({
    super.key,
    required this.apiClient,
    this.initialConfig,
  });

  static Future<void> show(
    BuildContext context, {
    required SteadyDevApiClient apiClient,
    TelemetryConfigData? initialConfig,
  }) async {
    await showDialog(
      context: context,
      builder: (ctx) => TelemetrySettingsDialog(
        apiClient: apiClient,
        initialConfig: initialConfig,
      ),
    );
  }

  @override
  State<TelemetrySettingsDialog> createState() => _TelemetrySettingsDialogState();
}

class _TelemetrySettingsDialogState extends State<TelemetrySettingsDialog> {
  bool _isLoading = false;
  bool _isSaving = false;
  bool _enabled = false;
  final TextEditingController _dsnController = TextEditingController();
  TelemetryConfigData? _config;
  String? _statusMessage;
  String? _errorMessage;

  @override
  void initState() {
    super.initState();
    if (widget.initialConfig != null) {
      _applyConfig(widget.initialConfig!);
    } else {
      _loadConfig();
    }
  }

  @override
  void dispose() {
    _dsnController.dispose();
    super.dispose();
  }

  void _applyConfig(TelemetryConfigData config) {
    _config = config;
    _enabled = config.enabled;
  }

  Future<void> _loadConfig() async {
    setState(() {
      _isLoading = true;
      _errorMessage = null;
    });

    try {
      final config = await widget.apiClient.getTelemetryConfig();
      if (mounted && config != null) {
        setState(() {
          _applyConfig(config);
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

  Future<void> _saveConfig() async {
    setState(() {
      _isSaving = true;
      _errorMessage = null;
      _statusMessage = null;
    });

    try {
      final dsnInput = _dsnController.text.trim();
      final updated = await widget.apiClient.updateTelemetryConfig(
        enabled: _enabled,
        dsn: dsnInput.isNotEmpty ? dsnInput : null,
      );

      if (mounted && updated != null) {
        setState(() {
          _applyConfig(updated);
          _isSaving = false;
          _statusMessage = updated.enabled
              ? 'Telemetry enabled (Export state: ${updated.exportState})'
              : 'Telemetry disabled (Unsent spans dropped)';
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isSaving = false;
          _errorMessage = e.toString();
        });
      }
    }
  }

  Color _getBadgeColor(String state, SteadyDevThemeTokens tokens) {
    switch (state) {
      case 'verified_delivered':
        return tokens.badgeConfirmedText;
      case 'local_only':
        return tokens.brandAction;
      case 'staged_local':
      case 'flushing':
        return tokens.badgeUnverifiedText;
      case 'delivery_failed':
        return tokens.badgeJudgmentText;
      default:
        return tokens.secondaryText;
    }
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
        children: [
          Icon(Icons.cloud_upload_outlined, color: tokens.brandAction, size: 22),
          const SizedBox(width: 10),
          Text(
            'Sentry Telemetry Settings',
            style: TextStyle(
              color: tokens.primaryText,
              fontSize: 18,
              fontWeight: FontWeight.bold,
            ),
          ),
        ],
      ),
      content: SizedBox(
        width: 580,
        child: _isLoading && _config == null
            ? const SizedBox(
                height: 200,
                child: Center(child: CircularProgressIndicator()),
              )
            : SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Opt-in Toggle
                    SwitchListTile(
                      contentPadding: EdgeInsets.zero,
                      title: Text(
                        'Enable Sentry Tracing Export',
                        style: TextStyle(
                          color: tokens.primaryText,
                          fontWeight: FontWeight.w600,
                          fontSize: 14,
                        ),
                      ),
                      subtitle: Text(
                        'Exports sanitized execution spans (timings, models, tokens) to Sentry',
                        style: TextStyle(
                          color: tokens.secondaryText,
                          fontSize: 12,
                        ),
                      ),
                      value: _enabled,
                      activeColor: tokens.brandAction,
                      onChanged: (val) {
                        setState(() {
                          _enabled = val;
                        });
                      },
                    ),
                    const SizedBox(height: 12),

                    // DSN Input Field
                    Text(
                      'Sentry DSN',
                      style: TextStyle(
                        color: tokens.primaryText,
                        fontWeight: FontWeight.w600,
                        fontSize: 13,
                      ),
                    ),
                    const SizedBox(height: 4),
                    TextField(
                      controller: _dsnController,
                      style: TextStyle(color: tokens.primaryText, fontSize: 13),
                      decoration: InputDecoration(
                        hintText: _config?.dsnConfigured == true
                            ? 'Configured: ${_config?.maskedDsn}'
                            : 'https://<key>@<host>/<project>',
                        hintStyle: TextStyle(color: tokens.secondaryText, fontSize: 12),
                        border: OutlineInputBorder(
                          borderRadius: BorderRadius.circular(6),
                          borderSide: BorderSide(color: tokens.dividerLine),
                        ),
                        contentPadding:
                            const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Irreversible Transmission and Privacy Disclosure Box
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: tokens.subtleSurface,
                        borderRadius: BorderRadius.circular(6),
                        border: Border.all(color: tokens.dividerLine),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.privacy_tip_outlined,
                                  size: 16, color: tokens.brandAction),
                              const SizedBox(width: 6),
                              Text(
                                'Data Privacy & Dispatch Disclosures',
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: 12,
                                  color: tokens.primaryText,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),
                          Text(
                            '• Strict Sanitization: Diffs, file contents, prompts, model output bodies, and local paths are scrubbed locally before export.\n'
                            '• Irreversible Dispatch: Data sent over TLS to Sentry cannot be recalled. Disabling during a review immediately drops unsent spans.\n'
                            '• Offline Core: Review, baseline, and diagnostics work 100% offline without Sentry.',
                            style: TextStyle(
                              fontSize: 11,
                              color: tokens.secondaryText,
                              height: 1.4,
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 16),

                    // Delivery & Export State Info
                    if (_config != null) ...[
                      Row(
                        children: [
                          Text(
                            'Export Status: ',
                            style: TextStyle(
                              fontSize: 12,
                              fontWeight: FontWeight.w600,
                              color: tokens.primaryText,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 2),
                            decoration: BoxDecoration(
                              color: _getBadgeColor(_config!.exportState, tokens)
                                  .withOpacity(0.15),
                              borderRadius: BorderRadius.circular(4),
                              border: Border.all(
                                color: _getBadgeColor(_config!.exportState, tokens),
                              ),
                            ),
                            child: Text(
                              _config!.exportState.toUpperCase(),
                              style: TextStyle(
                                fontSize: 11,
                                fontWeight: FontWeight.bold,
                                color: _getBadgeColor(_config!.exportState, tokens),
                              ),
                            ),
                          ),
                        ],
                      ),
                      if (_config!.lastTraceId != null) ...[
                        const SizedBox(height: 6),
                        Text(
                          'Last Trace ID: ${_config!.lastTraceId}',
                          style: TextStyle(
                            fontSize: 11,
                            fontFamily: 'monospace',
                            color: tokens.secondaryText,
                          ),
                        ),
                        if (_config!.traceUrl != null && _config!.verifiedDelivery) ...[
                          const SizedBox(height: 4),
                          SelectableText(
                            'Trace URL: ${_config!.traceUrl}',
                            style: TextStyle(
                              fontSize: 11,
                              color: tokens.brandAction,
                              decoration: TextDecoration.underline,
                            ),
                          ),
                        ],
                      ],
                    ],

                    if (_statusMessage != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _statusMessage!,
                        style: TextStyle(
                          color: tokens.brandAction,
                          fontSize: 12,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ],

                    if (_errorMessage != null) ...[
                      const SizedBox(height: 12),
                      Text(
                        _errorMessage!,
                        style: TextStyle(
                          color: tokens.badgeJudgmentText,
                          fontSize: 12,
                        ),
                      ),
                    ],
                  ],
                ),
              ),
      ),
      actions: [
        TextButton(
          onPressed: _isSaving ? null : () => Navigator.of(context).pop(),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: _isSaving ? null : _saveConfig,
          style: ElevatedButton.styleFrom(
            backgroundColor: tokens.brandAction,
            foregroundColor: Colors.white,
          ),
          child: _isSaving
              ? const SizedBox(
                  width: 14,
                  height: 14,
                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                )
              : const Text('Save Settings'),
        ),
      ],
    );
  }
}
