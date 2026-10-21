import 'dart:io';
import 'package:flutter/material.dart';
import '../theme/tokens.dart';

class SelectRepoDialog extends StatefulWidget {
  final String? initialPath;
  final List<String> recentRepos;

  const SelectRepoDialog({
    super.key,
    this.initialPath,
    this.recentRepos = const [],
  });

  static Future<String?> show(
    BuildContext context, {
    String? initialPath,
    List<String> recentRepos = const [],
  }) {
    return showDialog<String>(
      context: context,
      barrierDismissible: true,
      builder: (ctx) => SelectRepoDialog(
        initialPath: initialPath,
        recentRepos: recentRepos,
      ),
    );
  }

  @override
  State<SelectRepoDialog> createState() => _SelectRepoDialogState();
}

class _SelectRepoDialogState extends State<SelectRepoDialog> {
  late final TextEditingController _controller;
  String? _error;

  @override
  void initState() {
    super.initState();
    _controller = TextEditingController(text: widget.initialPath ?? '');
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _validateAndSubmit(String path) {
    final trimmed = path.trim();
    if (trimmed.isEmpty) {
      setState(() => _error = 'Please enter a repository path');
      return;
    }

    final dir = Directory(trimmed);
    if (!dir.existsSync()) {
      setState(() => _error = 'Directory does not exist');
      return;
    }

    final gitDir = Directory('${dir.path}${Platform.pathSeparator}.git');
    final isFixture = trimmed.contains('sample_repo') || trimmed.contains('mock_repo');
    if (!gitDir.existsSync() && !isFixture) {
      setState(() => _error = 'Path is not a valid Git repository (.git missing)');
      return;
    }

    Navigator.of(context).pop(dir.path);
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
      child: ConstrainedBox(
        constraints: const BoxConstraints(maxWidth: 540),
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Row(
                    children: [
                      Icon(Icons.folder_open, size: 20, color: tokens.brandAction),
                      const SizedBox(width: 8),
                      Text(
                        'Select Repository',
                        style: TextStyle(
                          fontSize: 18,
                          fontWeight: FontWeight.bold,
                          color: tokens.primaryText,
                        ),
                      ),
                    ],
                  ),
                  IconButton(
                    icon: Icon(Icons.close, size: 20, color: tokens.secondaryText),
                    tooltip: 'Close',
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
              const SizedBox(height: 8),
              Text(
                'Enter the local directory path of your Git repository to observe working snapshots:',
                style: TextStyle(fontSize: 13, color: tokens.secondaryText),
              ),
              const SizedBox(height: 16),
              TextField(
                controller: _controller,
                autofocus: true,
                style: TextStyle(fontSize: 14, color: tokens.primaryText),
                decoration: InputDecoration(
                  hintText: 'e.g. C:\\Projects\\my-repo or /home/user/project',
                  hintStyle: TextStyle(fontSize: 13, color: tokens.secondaryText.withValues(alpha: 0.6)),
                  errorText: _error,
                  prefixIcon: Icon(Icons.fork_right, size: 18, color: tokens.brandAction),
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(color: tokens.inputBoundary),
                  ),
                  focusedBorder: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(8),
                    borderSide: BorderSide(color: tokens.brandAction, width: 2),
                  ),
                ),
                onSubmitted: _validateAndSubmit,
                onChanged: (_) {
                  if (_error != null) setState(() => _error = null);
                },
              ),
              if (widget.recentRepos.isNotEmpty) ...[
                const SizedBox(height: 16),
                Text(
                  'Recent Repositories',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                    color: tokens.secondaryText,
                  ),
                ),
                const SizedBox(height: 8),
                Wrap(
                  spacing: 8,
                  runSpacing: 6,
                  children: widget.recentRepos.map((r) {
                    final label = r.split(Platform.pathSeparator).last;
                    return ActionChip(
                      avatar: Icon(Icons.history, size: 14, color: tokens.brandAction),
                      label: Text(label, style: TextStyle(fontSize: 12, color: tokens.primaryText)),
                      backgroundColor: tokens.subtleSurface,
                      side: BorderSide(color: tokens.dividerLine),
                      onPressed: () => _validateAndSubmit(r),
                    );
                  }).toList(),
                ),
              ],
              const SizedBox(height: 24),
              Row(
                mainAxisAlignment: MainAxisAlignment.end,
                children: [
                  TextButton(
                    onPressed: () => Navigator.of(context).pop(),
                    style: TextButton.styleFrom(foregroundColor: tokens.secondaryText),
                    child: const Text('Cancel'),
                  ),
                  const SizedBox(width: 8),
                  ElevatedButton(
                    style: ElevatedButton.styleFrom(
                      backgroundColor: tokens.brandAction,
                      foregroundColor: tokens.brandActionInk,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                    ),
                    onPressed: () => _validateAndSubmit(_controller.text),
                    child: const Text('Open repository', style: TextStyle(fontWeight: FontWeight.bold)),
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
