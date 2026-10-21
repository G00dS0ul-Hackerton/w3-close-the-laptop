import 'package:flutter/material.dart';

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
  String _repoName = 'sample-project';
  String _intention = 'Fix the login redirect and make the dashboard work on mobile.';
  final List<String> _criteria = [
    'Correct destination',
    'Mobile navigation',
    'No auth regressions',
  ];
  List<FindingItem> _findings = [];
  bool _isReviewing = false;
  bool _isPaused = false;
  bool _isEnded = false;
  String _quietStatus = 'Ready for checkpoint';
  String _restartNote =
      'Open the dashboard at 390px and check mobile navigation. The login redirect change has sample auth-test evidence.';

  @override
  void initState() {
    super.initState();
    _loadInitialSampleData();
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
          repoPath: '',
          intention: _intention,
          criteria: _criteria,
          receipts: [],
          priorFindings: _findings,
        );

        if (res != null) {
          setState(() {
            _findings = res.findings;
            _quietStatus = 'Checkpoint complete';
            if (res.restartNote.isNotEmpty) {
              _restartNote = res.restartNote;
            }
          });
        }
      } on ApiException catch (e) {
        setState(() {
          _quietStatus = e.code == 'model_unavailable' ? 'Local model offline' : 'Review failed: ${e.message}';
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
                              child: Row(
                                mainAxisSize: MainAxisSize.min,
                                children: [
                                  if (showBadges) ...[
                                    Text('Workspace', style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                                    const SizedBox(width: 6),
                                    Text('/', style: TextStyle(fontSize: 13, color: tokens.secondaryText)),
                                    const SizedBox(width: 6),
                                  ],
                                  Icon(Icons.fork_right, size: 16, color: tokens.secondaryText),
                                  const SizedBox(width: 4),
                                  Text(
                                    _repoName,
                                    style: TextStyle(
                                        fontSize: 14, fontWeight: FontWeight.bold, color: tokens.primaryText),
                                  ),
                                ],
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
                          isReviewing: _isReviewing,
                          isPaused: _isPaused,
                          isEnded: _isEnded,
                          quietStatus: _quietStatus,
                          onTriggerCheckpoint: _triggerCheckpoint,
                          onTogglePause: () => setState(() => _isPaused = !_isPaused),
                          onNavigateToClosing: () => setState(() => _activeView = 'closing'),
                          onUpdateIntention: (val) => setState(() => _intention = val),
                          onUpdateFindingStatus: _updateFindingStatus,
                        )
                      : _activeView == 'audit'
                          ? AuditView(
                              findings: _findings,
                              onUpdateFindingStatus: _updateFindingStatus,
                            )
                          : ClosingView(
                              findings: _findings,
                              initialRestartNote: _restartNote,
                              isEnded: _isEnded,
                              onBackToSession: () => setState(() => _activeView = 'session'),
                              onFinalizeSession: () {
                                setState(() {
                                  _isEnded = true;
                                  _isPaused = true;
                                });
                                ScaffoldMessenger.of(context).showSnackBar(
                                  const SnackBar(
                                    content: Text('Session closed. Your restart note is ready.'),
                                    duration: Duration(seconds: 3),
                                  ),
                                );
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
