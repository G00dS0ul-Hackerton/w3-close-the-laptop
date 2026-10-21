import 'dart:io';
import 'package:flutter/material.dart';

import '../dialogs/select_repo_dialog.dart';
import '../models/session_models.dart';
import '../services/api_client.dart';
import '../theme/theme_manager.dart';
import '../theme/tokens.dart';
import '../views/audit_view.dart';
import '../views/closing_view.dart';
import '../views/session_view.dart';

class SteadyDevScaffold extends StatefulWidget {
  final ThemeManager themeManager;
  final SteadyDevApiClient? apiClient;

  const SteadyDevScaffold({
    super.key,
    required this.themeManager,
    this.apiClient,
  });

  @override
  State<SteadyDevScaffold> createState() => _SteadyDevScaffoldState();
}

class _SteadyDevScaffoldState extends State<SteadyDevScaffold> {
  String _activeView = 'session';
  String _repoPath = '';
  String _repoName = 'sample-project';
  bool _isCleanWorkingTree = false;
  bool _isEngineOffline = false;
  String _intention = 'Fix the login redirect and make the dashboard work on mobile.';
  final List<String> _criteria = [
    'Correct destination',
    'Mobile navigation',
    'No auth regressions',
  ];
  List<FindingItem> _findings = [];
  List<SessionCheckReceipt> _receipts = [];
  bool _isReviewing = false;
  bool _isPaused = false;
  bool _isEnded = false;
  bool _isNoteUserEdited = false;
  String? _activeEngineTier;
  String _quietStatus = 'Ready for checkpoint';
  String _restartNote =
      'Open the dashboard at 390px and check mobile navigation. The login redirect change has sample auth-test evidence.';

  @override
  void initState() {
    super.initState();
    if (widget.apiClient == null) {
      _loadInitialSampleData();
    } else {
      _loadSessionFromEngine();
    }
  }

  Future<void> _loadSessionFromEngine() async {
    try {
      final sessionData = await widget.apiClient!.getActiveSession();
      if (!mounted) return;
      setState(() {
        if (sessionData.repoPath.isNotEmpty) _repoPath = sessionData.repoPath;
        if (sessionData.repoName.isNotEmpty) _repoName = sessionData.repoName;
        if (sessionData.intention.isNotEmpty) _intention = sessionData.intention;
        if (sessionData.criteria.isNotEmpty) {
          _criteria.clear();
          _criteria.addAll(sessionData.criteria);
        }
        _findings = sessionData.findings;
        _receipts = sessionData.checkReceipts;
        if (sessionData.restartNote.isNotEmpty) {
          _restartNote = sessionData.restartNote;
        }
        _isNoteUserEdited = sessionData.isNoteUserEdited;
        _isEnded = sessionData.isEnded;
        _isPaused = sessionData.isEnded;
        _isCleanWorkingTree = sessionData.gitStatus?.state == 'clean';
        _isEngineOffline = false;
        _quietStatus = _isCleanWorkingTree ? 'Working tree clean' : 'Ready for checkpoint';
      });
    } on ApiException catch (e) {
      if (!mounted) return;
      setState(() {
        if (e.code == 'engine_offline') {
          _isEngineOffline = true;
          _quietStatus = 'Engine offline · Reconnect to review';
        } else {
          _quietStatus = 'Error: ${e.message}';
        }
      });
    } catch (_) {
      // Graceful fallback to initial sample data
    }
  }

  Future<void> _openSelectRepoDialog() async {
    List<String> recents = [];
    if (widget.apiClient != null) {
      try {
        final recentList = await widget.apiClient!.getRecentRepos();
        recents = recentList
            .map((r) => r['repo_path'] as String? ?? '')
            .where((p) => p.isNotEmpty)
            .toList();
      } catch (_) {}
    }

    if (!mounted) return;
    final selected = await SelectRepoDialog.show(
      context,
      initialPath: _repoPath.isNotEmpty ? _repoPath : null,
      recentRepos: recents,
    );

    if (selected != null && selected.isNotEmpty) {
      await _onRepoSelected(selected);
    }
  }

  Future<void> _onRepoSelected(String path) async {
    setState(() {
      _repoPath = path;
      _repoName = path.split(Platform.pathSeparator).last;
      _quietStatus = 'Connecting to repository...';
    });

    if (widget.apiClient != null) {
      try {
        final session = await widget.apiClient!.selectRepo(path);
        if (!mounted) return;
        setState(() {
          _repoPath = session.repoPath.isNotEmpty ? session.repoPath : path;
          _repoName = session.repoName.isNotEmpty ? session.repoName : _repoName;
          _intention = session.intention;
          if (session.criteria.isNotEmpty) {
            _criteria.clear();
            _criteria.addAll(session.criteria);
          }
          _findings = session.findings;
          _receipts = session.checkReceipts;
          _restartNote = session.restartNote;
          _isNoteUserEdited = session.isNoteUserEdited;
          _isEnded = session.isEnded;
          _isPaused = session.isEnded;
          _isCleanWorkingTree = session.gitStatus?.state == 'clean';
          _isEngineOffline = false;
          _quietStatus = _isCleanWorkingTree ? 'Working tree clean' : 'Ready for checkpoint';
        });
      } on ApiException catch (e) {
        if (!mounted) return;
        setState(() {
          if (e.code == 'engine_offline') {
            _isEngineOffline = true;
            _quietStatus = 'Engine offline';
          } else {
            _quietStatus = 'Selection failed: ${e.message}';
          }
        });
      } catch (e) {
        if (!mounted) return;
        setState(() {
          _quietStatus = 'Error selecting repo: $e';
        });
      }
    }
  }

  void _loadInitialSampleData() {
    _findings = [
      FindingItem(
        id: 'mobile-01',
        title: 'The mobile check is still unrecorded.',
        description:
            'Dashboard styles changed. No visual check at the agreed mobile viewport appears in the evidence.',
        locator: 'src/dashboard.css · lines 42–58',
        type: FindingType.unverified,
        lifecycle: FindingLifecycle.open,
        receiptSnippet:
            'SESSION CRITERION\nMobile navigation works at 390px.\n\nRECORDED CHECKS\nAuth suite only. No viewport check attached.',
        limit:
            'This is an evidence gap, not a confirmed layout bug. You may have checked it outside the tool.',
      ),
      FindingItem(
        id: 'readme-01',
        title: 'The README may describe the old destination.',
        description:
            'The redirect now points to /dashboard. The setup guide still says /welcome. Decide whether that wording needs to change.',
        locator: 'src/auth/redirect.ts:18 · README.md:34',
        type: FindingType.needsJudgment,
        lifecycle: FindingLifecycle.open,
        receiptSnippet:
            'ILLUSTRATIVE CHANGE\nsrc/auth/redirect.ts:18\nreturn "/dashboard";\n\nDOCUMENT\nREADME.md:34\n"After signing in, you arrive at /welcome."',
        limit:
            'This could be stale documentation or an intentional distinction. The reviewer cannot decide which.',
      ),
      FindingItem(
        id: 'auth-err-01',
        title: 'The error-state check now has evidence.',
        description: 'The test receipt includes the missing error-state assertion. This earlier gap has been retired.',
        locator: 'tests/auth.spec.ts:71',
        type: FindingType.confirmed,
        lifecycle: FindingLifecycle.resolved,
        receiptSnippet: 'Authentication checks: 6 passed\nIncludes: invalid session shows error state',
        limit: 'These checks do not establish mobile layout, accessibility, or complete application correctness.',
        reason: 'Resolved by receipt: error-state assertion recorded.',
      ),
    ];
  }

  Future<void> _triggerCheckpoint() async {
    if (_isReviewing || _isPaused || _isEnded) return;

    setState(() {
      _isReviewing = true;
      _quietStatus = 'Reviewing snapshot with Ollama...';
    });

    if (widget.apiClient != null) {
      try {
        final res = await widget.apiClient!.requestReview(
          repoPath: _repoPath,
          intention: _intention,
          criteria: _criteria,
          receipts: _receipts,
          priorFindings: _findings,
        );

        if (res != null) {
          setState(() {
            // Reconcile findings while protecting user lifecycle decisions
            final existingMap = {for (var f in _findings) f.id: f};
            final mergedFindings = <FindingItem>[];

            for (final newF in res.findings) {
              if (existingMap.containsKey(newF.id)) {
                final existing = existingMap[newF.id]!;
                if (existing.lifecycle != FindingLifecycle.open) {
                  newF.lifecycle = existing.lifecycle;
                  newF.reason = existing.reason;
                }
              }
              mergedFindings.add(newF);
            }

            // Mark retired findings
            for (final rid in res.retiredFindingIds) {
              final match = existingMap[rid];
              if (match != null) {
                match.lifecycle = FindingLifecycle.evidenceRetired;
                if (!mergedFindings.any((f) => f.id == match.id)) {
                  mergedFindings.add(match);
                }
              }
            }

            _findings = mergedFindings;
            _quietStatus = 'Checkpoint complete';
            _activeEngineTier = res.modelTag;
            if (!_isNoteUserEdited && res.restartNote.isNotEmpty) {
              _restartNote = res.restartNote;
            }
          });
        }
      } on ApiException catch (e) {
        setState(() {
          if (e.code == 'engine_offline') {
            _isEngineOffline = true;
            _quietStatus = 'Engine offline · Reconnect to review';
          } else if (e.code == 'model_unavailable') {
            _quietStatus = 'Local model offline';
          } else if (e.code == 'conflict') {
            _quietStatus = 'Snapshot conflict: working tree modified';
          } else {
            _quietStatus = 'Review failed: ${e.message}';
          }
        });
      } catch (e) {
        setState(() {
          _quietStatus = 'Review error: $e';
        });
      }
    } else {
      // Offline fallback simulation
      await Future.delayed(const Duration(milliseconds: 600));
      setState(() {
        _quietStatus = 'Checkpoint complete (local cache)';
      });
    }

    setState(() {
      _isReviewing = false;
    });
  }

  void _updateFindingStatus(FindingItem finding, FindingLifecycle status, String? reason) {
    setState(() {
      finding.lifecycle = status;
      finding.reason = reason;
    });
    widget.apiClient?.updateFindingStatus(
      findingId: finding.id,
      status: finding.statusString,
      userReason: reason,
    );
  }

  Future<void> _resetSession() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) {
        final tokens = Theme.of(ctx).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;
        return AlertDialog(
          backgroundColor: tokens.panel,
          title: Text('Start a new session?', style: TextStyle(color: tokens.primaryText, fontSize: 16)),
          content: Text(
            'This will archive the current session and let you start fresh. Any previous deferred or resolved findings will be cleared from this view.',
            style: TextStyle(color: tokens.secondaryText, fontSize: 13, height: 1.4),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(ctx).pop(false),
              child: Text('Cancel', style: TextStyle(color: tokens.secondaryText)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(
                backgroundColor: tokens.brandAction,
                foregroundColor: tokens.brandActionInk,
              ),
              onPressed: () => Navigator.of(ctx).pop(true),
              child: const Text('Start fresh'),
            ),
          ],
        );
      },
    );

    if (confirmed != true) return;

    if (widget.apiClient != null) {
      try {
        final freshSession = await widget.apiClient!.resetSession(
          repoPath: _repoPath,
          intention: _intention,
          criteria: _criteria,
        );
        if (!mounted) return;
        setState(() {
          _findings.clear();
          _receipts.clear();
          _restartNote = freshSession.restartNote;
          _isNoteUserEdited = false;
          _isEnded = false;
          _isPaused = false;
          _activeEngineTier = null;
          _isCleanWorkingTree = freshSession.gitStatus?.state == 'clean';
          _quietStatus = 'Fresh session started · Ready for checkpoint';
        });
      } on ApiException catch (e) {
        if (!mounted) return;
        setState(() {
          _quietStatus = 'Reset failed: ${e.message}';
        });
      }
    } else {
      setState(() {
        _findings.clear();
        _receipts.clear();
        _isEnded = false;
        _isPaused = false;
        _quietStatus = 'Fresh session started (local)';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final tokens = Theme.of(context).extension<SteadyDevThemeTokens>() ?? SteadyDevThemeTokens.light;

    return Scaffold(
      backgroundColor: tokens.canvas,
      body: Row(
        children: [
          // Sidebar
          Container(
            width: 220,
            decoration: BoxDecoration(
              color: tokens.panel,
              border: Border(right: BorderSide(color: tokens.dividerLine)),
            ),
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Brand Header
                Row(
                  children: [
                    Container(
                      width: 38,
                      height: 38,
                      decoration: BoxDecoration(
                        color: tokens.softBrandSurface,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: tokens.brandOutline),
                      ),
                      child: Icon(Icons.laptop_chromebook, color: tokens.brandAction, size: 20),
                    ),
                    const SizedBox(width: 10),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            'SteadyDev',
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.bold,
                              color: tokens.primaryText,
                            ),
                          ),
                          Text(
                            'Close the Laptop',
                            overflow: TextOverflow.ellipsis,
                            style: TextStyle(fontSize: 11, color: tokens.secondaryText),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 32),

                Text(
                  'YOUR WORKDAY',
                  style: TextStyle(
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                    letterSpacing: 1.1,
                    color: tokens.secondaryText,
                  ),
                ),
                const SizedBox(height: 12),

                // Nav Items
                _buildNavButton(tokens, 'session', 'Session', Icons.wb_sunny_outlined),
                const SizedBox(height: 4),
                _buildNavButton(tokens, 'audit', 'Quiet audit', Icons.layers_outlined),
                const SizedBox(height: 4),
                _buildNavButton(tokens, 'closing', 'Closing card', Icons.nightlight_round),

                const Spacer(),
                Divider(color: tokens.dividerLine),
                const SizedBox(height: 12),
                Text(
                  'A second pair of eyes.\nNot another manager.',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: tokens.primaryText, height: 1.3),
                ),
                const SizedBox(height: 4),
                Text(
                  'Local review companion.',
                  style: TextStyle(fontSize: 11, color: tokens.secondaryText),
                ),
              ],
            ),
          ),

          // Main Content Area
          Expanded(
            child: Column(
              children: [
                // Top Bar
                LayoutBuilder(
                  builder: (context, topBarConstraints) {
                    final showBadges = topBarConstraints.maxWidth > 420;

                    return Container(
                      height: 64,
                      padding: EdgeInsets.symmetric(horizontal: showBadges ? 24 : 12),
                      decoration: BoxDecoration(
                        color: tokens.panel,
                        border: Border(bottom: BorderSide(color: tokens.dividerLine)),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          // Breadcrumb
                          Flexible(
                            child: SingleChildScrollView(
                              scrollDirection: Axis.horizontal,
                              child: InkWell(
                                onTap: _openSelectRepoDialog,
                                borderRadius: BorderRadius.circular(6),
                                child: Padding(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
                                  child: Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      if (showBadges) ...[
                                        Text('Workspace', style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                                        const SizedBox(width: 6),
                                        Text('/', style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                                        const SizedBox(width: 6),
                                      ],
                                      Icon(Icons.fork_right, size: 16, color: tokens.brandAction),
                                      const SizedBox(width: 4),
                                      Text(
                                        _repoName,
                                        style: TextStyle(
                                            fontSize: 14, fontWeight: FontWeight.bold, color: tokens.primaryText),
                                      ),
                                      const SizedBox(width: 4),
                                      Icon(Icons.arrow_drop_down, size: 18, color: tokens.secondaryText),
                                    ],
                                  ),
                                ),
                              ),
                            ),
                          ),
                          const SizedBox(width: 8),

                          // Actions & Theme
                          Flexible(
                            child: SingleChildScrollView(
                              scrollDirection: Axis.horizontal,
                              reverse: true,
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (showBadges) ...[
                                    Text('Theme', style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                                    const SizedBox(width: 8),
                                  ],
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                    decoration: BoxDecoration(
                                      border: Border.all(color: tokens.inputBoundary),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: DropdownButtonHideUnderline(
                                      child: DropdownButton<ThemeMode>(
                                        value: widget.themeManager.themeMode,
                                        isDense: true,
                                        icon: const Icon(Icons.arrow_drop_down, size: 18),
                                        style: TextStyle(fontSize: 13, color: tokens.primaryText),
                                        dropdownColor: tokens.panel,
                                        items: const [
                                          DropdownMenuItem(value: ThemeMode.system, child: Text('System')),
                                          DropdownMenuItem(value: ThemeMode.light, child: Text('Light')),
                                          DropdownMenuItem(value: ThemeMode.dark, child: Text('Dark')),
                                        ],
                                        onChanged: (mode) {
                                          if (mode != null) {
                                            widget.themeManager.setThemeMode(mode);
                                          }
                                        },
                                      ),
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  OutlinedButton.icon(
                                    style: OutlinedButton.styleFrom(
                                      foregroundColor: tokens.primaryText,
                                      side: BorderSide(color: tokens.inputBoundary),
                                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                                    ),
                                    icon: Icon(Icons.restart_alt, size: 16, color: tokens.brandAction),
                                    label: const Text('New session', style: TextStyle(fontSize: 12)),
                                    onPressed: _resetSession,
                                  ),
                                  if (showBadges) ...[
                                    const SizedBox(width: 12),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: tokens.softBrandSurface,
                                        borderRadius: BorderRadius.circular(6),
                                        border: Border.all(color: tokens.brandOutline),
                                      ),
                                      child: Text(
                                        'Live Desktop',
                                        style: TextStyle(
                                            fontSize: 12,
                                            fontWeight: FontWeight.bold,
                                            color: tokens.brandAction),
                                      ),
                                    ),
                                  ],
                                  const SizedBox(width: 10),
                                  CircleAvatar(
                                    radius: 16,
                                    backgroundColor: tokens.subtleSurface,
                                    child: Text('AY',
                                        style: TextStyle(
                                            fontSize: 12, fontWeight: FontWeight.bold, color: tokens.primaryText)),
                                  ),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    );
                  },
                ),

                // Active View
                Expanded(
                  child: _activeView == 'session'
                      ? SessionView(
                          repoName: _repoName,
                          intention: _intention,
                          criteria: _criteria,
                          findings: _findings,
                          receipts: _receipts,
                          isReviewing: _isReviewing,
                          isPaused: _isPaused,
                          isEnded: _isEnded,
                          quietStatus: _quietStatus,
                          isCleanWorkingTree: _isCleanWorkingTree,
                          isEngineOffline: _isEngineOffline,
                          activeEngine: _activeEngineTier,
                          onRetryConnection: _loadSessionFromEngine,
                          onSelectRepo: _openSelectRepoDialog,
                          onTriggerCheckpoint: _triggerCheckpoint,
                          onTogglePause: () => setState(() => _isPaused = !_isPaused),
                          onNavigateToClosing: () => setState(() => _activeView = 'closing'),
                          onUpdateIntention: (val) {
                            setState(() => _intention = val);
                            widget.apiClient?.updateSessionIntention(
                              repoPath: _repoPath,
                              intention: val,
                              criteria: _criteria,
                            );
                          },
                          onUpdateFindingStatus: _updateFindingStatus,
                        )
                      : _activeView == 'audit'
                          ? AuditView(
                              findings: _findings,
                              onUpdateFindingStatus: _updateFindingStatus,
                            )
                          : ClosingView(
                              findings: _findings,
                              receipts: _receipts,
                              changedFileCount: _findings.length,
                              initialRestartNote: _restartNote,
                              isEnded: _isEnded,
                              onRestartNoteChanged: (newNote) {
                                _restartNote = newNote;
                                _isNoteUserEdited = true;
                                widget.apiClient?.updateRestartNote(
                                  repoPath: _repoPath,
                                  restartNote: newNote,
                                  isUserEdited: true,
                                );
                              },
                              onBackToSession: () => setState(() => _activeView = 'session'),
                              onFinalizeSession: (finalNote) async {
                                setState(() {
                                  _restartNote = finalNote;
                                  _isNoteUserEdited = true;
                                  _isEnded = true;
                                  _isPaused = true;
                                });
                                if (widget.apiClient != null) {
                                  await widget.apiClient!.updateRestartNote(
                                    repoPath: _repoPath,
                                    restartNote: finalNote,
                                    isUserEdited: true,
                                  );
                                  await widget.apiClient!.closeSession(
                                    repoPath: _repoPath,
                                    closingSummary: {
                                      'closed_at': DateTime.now().toIso8601String(),
                                      'unresolved_findings': _findings
                                          .where((f) => f.lifecycle == FindingLifecycle.open)
                                          .length,
                                    },
                                  );
                                }
                                if (mounted) {
                                  ScaffoldMessenger.of(context).showSnackBar(
                                    const SnackBar(
                                      content: Text('Session closed. Your restart note is ready.'),
                                      duration: Duration(seconds: 3),
                                    ),
                                  );
                                }
                              },
                            ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNavButton(SteadyDevThemeTokens tokens, String viewKey, String label, IconData icon) {
    final isSelected = _activeView == viewKey;

    return InkWell(
      borderRadius: BorderRadius.circular(8),
      onTap: () => setState(() => _activeView = viewKey),
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
        decoration: BoxDecoration(
          color: isSelected ? tokens.softBrandSurface : Colors.transparent,
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          children: [
            Icon(
              icon,
              size: 18,
              color: isSelected ? tokens.brandAction : tokens.secondaryText,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                label,
                overflow: TextOverflow.ellipsis,
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
                  color: isSelected ? tokens.brandAction : tokens.secondaryText,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}
