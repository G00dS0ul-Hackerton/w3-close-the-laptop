import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../theme/tokens.dart';

/// In-app startup error boundary view displaying actionable failure guidance,
/// sanitized diagnostics snippet, retry trigger, and log locator.
class StartupErrorView extends StatefulWidget {
  final String errorMessage;
  final String? logPath;
  final List<String> recentStderr;
  final VoidCallback onRetry;
  final VoidCallback? onDismissOffline;

  const StartupErrorView({
    super.key,
    required this.errorMessage,
    this.logPath,
    this.recentStderr = const [],
    required this.onRetry,
    this.onDismissOffline,
  });

  @override
  State<StartupErrorView> createState() => _StartupErrorViewState();
}

class _StartupErrorViewState extends State<StartupErrorView> {
  bool _isCopied = false;
  bool _showDetails = false;

  void _copyLogPath() {
    if (widget.logPath != null) {
      Clipboard.setData(ClipboardData(text: widget.logPath!));
      setState(() {
        _isCopied = true;
      });
      Future.delayed(const Duration(seconds: 2), () {
        if (mounted) {
          setState(() {
            _isCopied = false;
          });
        }
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ??
        SteadyDevThemeTokens.light;
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
        child: Container(
          constraints: const BoxConstraints(maxWidth: 640),
          decoration: BoxDecoration(
            color: tokens.panel,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: tokens.dividerLine),
            boxShadow: [
              BoxShadow(
                color: Colors.black.withValues(alpha: 0.06),
                blurRadius: 16,
                offset: const Offset(0, 4),
              ),
            ],
          ),
          padding: const EdgeInsets.all(28),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header Row with Alert Icon and Brand
              Row(
                children: [
                  Container(
                    width: 44,
                    height: 44,
                    decoration: BoxDecoration(
                      color: tokens.badgeJudgmentBg,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(
                      Icons.warning_amber_rounded,
                      color: tokens.badgeJudgmentText,
                      size: 26,
                    ),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'SteadyDev Engine Offline',
                          style: TextStyle(
                            fontSize: 18,
                            fontWeight: FontWeight.bold,
                            color: tokens.primaryText,
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          'Local Python loopback service failed to start or respond',
                          style: TextStyle(
                            fontSize: 12,
                            color: tokens.secondaryText,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 20),

              // Error Message
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: tokens.subtleSurface,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: tokens.dividerLine),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.info_outline,
                      size: 16,
                      color: tokens.secondaryText,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        widget.errorMessage,
                        style: TextStyle(
                          fontSize: 13,
                          color: tokens.primaryText,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),

              // Log File Locator
              if (widget.logPath != null) ...[
                Text(
                  'DIAGNOSTICS LOG',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.1,
                    color: tokens.secondaryText,
                  ),
                ),
                const SizedBox(height: 6),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 12,
                    vertical: 8,
                  ),
                  decoration: BoxDecoration(
                    color: tokens.subtleSurface,
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(color: tokens.inputBoundary),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.description_outlined,
                        size: 16,
                        color: tokens.secondaryText,
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          widget.logPath!,
                          style: const TextStyle(
                            fontSize: 12,
                            fontFamily: 'Consolas',
                          ),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ),
                      const SizedBox(width: 8),
                      TextButton.icon(
                        onPressed: _copyLogPath,
                        icon: Icon(
                          _isCopied ? Icons.check : Icons.copy,
                          size: 14,
                        ),
                        label: Text(_isCopied ? 'Copied' : 'Copy Path'),
                        style: TextButton.styleFrom(
                          padding: const EdgeInsets.symmetric(
                            horizontal: 8,
                            vertical: 4,
                          ),
                          textStyle: const TextStyle(fontSize: 11),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 16),
              ],

              // Stderr snippet if available
              if (widget.recentStderr.isNotEmpty) ...[
                InkWell(
                  onTap: () {
                    setState(() {
                      _showDetails = !_showDetails;
                    });
                  },
                  borderRadius: BorderRadius.circular(4),
                  child: Padding(
                    padding: const EdgeInsets.symmetric(vertical: 4),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(
                          _showDetails
                              ? Icons.expand_less
                              : Icons.expand_more,
                          size: 18,
                          color: tokens.brandAction,
                        ),
                        const SizedBox(width: 4),
                        Text(
                          _showDetails
                              ? 'Hide stderr diagnostics'
                              : 'Show stderr diagnostics (${widget.recentStderr.length} lines)',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: tokens.brandAction,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                if (_showDetails) ...[
                  const SizedBox(height: 8),
                  Container(
                    width: double.infinity,
                    constraints: const BoxConstraints(maxHeight: 180),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF181B18) : const Color(0xFF222622),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: SingleChildScrollView(
                      child: SelectableText(
                        widget.recentStderr.join('\n'),
                        style: const TextStyle(
                          color: Color(0xFFE2E8F0),
                          fontFamily: 'Consolas',
                          fontSize: 11,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ),
                ],
                const SizedBox(height: 16),
              ],

              const SizedBox(height: 8),

              // Action buttons
              Wrap(
                spacing: 12,
                runSpacing: 10,
                children: [
                  ElevatedButton.icon(
                    onPressed: widget.onRetry,
                    icon: const Icon(Icons.refresh, size: 16),
                    label: const Text('Retry Startup'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: tokens.brandAction,
                      foregroundColor: tokens.brandActionInk,
                      padding: const EdgeInsets.symmetric(
                        horizontal: 18,
                        vertical: 12,
                      ),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                    ),
                  ),
                  if (widget.onDismissOffline != null)
                    OutlinedButton.icon(
                      onPressed: widget.onDismissOffline,
                      icon: const Icon(Icons.offline_bolt_outlined, size: 16),
                      label: const Text('Work Offline (Sample Data)'),
                      style: OutlinedButton.styleFrom(
                        foregroundColor: tokens.primaryText,
                        side: BorderSide(color: tokens.inputBoundary),
                        padding: const EdgeInsets.symmetric(
                          horizontal: 16,
                          vertical: 12,
                        ),
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(8),
                        ),
                      ),
                    ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
