import 'dart:convert';
import 'package:http/http.dart' as http;

import '../models/session_models.dart';

class ApiException implements Exception {
  final String code;
  final String message;
  final int statusCode;

  ApiException(this.code, this.message, [this.statusCode = 500]);

  @override
  String toString() => 'ApiException($code: $message)';
}

class SteadyDevApiClient {
  final String baseUrl;
  final String token;
  final http.Client _client;
  int _latestRequestId = 0;

  SteadyDevApiClient({
    required this.baseUrl,
    required this.token,
    http.Client? client,
  }) : _client = client ?? http.Client();

  Map<String, String> get _authHeaders => {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': 'Bearer $token',
      };

  Future<http.Response> _safeGet(Uri url) async {
    try {
      return await _client.get(url, headers: _authHeaders);
    } on http.ClientException catch (e) {
      throw ApiException(
          'engine_offline', 'Cannot reach local engine at $baseUrl: ${e.message}', 503);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('engine_offline', 'Cannot reach local engine at $baseUrl: $e', 503);
    }
  }

  Future<http.Response> _safePost(Uri url, {Object? body}) async {
    try {
      return await _client.post(url, headers: _authHeaders, body: body);
    } on http.ClientException catch (e) {
      throw ApiException(
          'engine_offline', 'Cannot reach local engine at $baseUrl: ${e.message}', 503);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('engine_offline', 'Cannot reach local engine at $baseUrl: $e', 503);
    }
  }

  Future<http.Response> _safePatch(Uri url, {Object? body}) async {
    try {
      return await _client.patch(url, headers: _authHeaders, body: body);
    } on http.ClientException catch (e) {
      throw ApiException(
          'engine_offline', 'Cannot reach local engine at $baseUrl: ${e.message}', 503);
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('engine_offline', 'Cannot reach local engine at $baseUrl: $e', 503);
    }
  }

  /// Check engine health and Ollama model status.
  Future<Map<String, dynamic>> checkHealth() async {
    final res = await _safeGet(Uri.parse('$baseUrl/api/health'));
    if (res.statusCode == 200) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    } else if (res.statusCode == 401) {
      throw ApiException('unauthorized', 'Authentication required', 401);
    } else {
      throw ApiException('error', 'Health check failed: ${res.statusCode}', res.statusCode);
    }
  }

  /// Request snapshot summary from git collector.
  Future<Map<String, dynamic>> getSnapshot(String repoPath) async {
    final res = await _safePost(
      Uri.parse('$baseUrl/api/snapshot'),
      body: jsonEncode({'repo_path': repoPath}),
    );

    if (res.statusCode == 200) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    } else if (res.statusCode == 403) {
      throw ApiException('forbidden', 'Repository outside authorized boundary', 403);
    } else {
      throw ApiException('error', 'Snapshot failed', res.statusCode);
    }
  }

  /// Validate repository path against server security boundary.
  Future<Map<String, dynamic>> validateRepo(String repoPath) async {
    final res = await _safePost(
      Uri.parse('$baseUrl/api/repo/validate'),
      body: jsonEncode({'repo_path': repoPath}),
    );
    if (res.statusCode == 200) {
      return jsonDecode(res.body) as Map<String, dynamic>;
    } else {
      final err = jsonDecode(res.body) as Map<String, dynamic>;
      throw ApiException(
          err['error'] ?? 'invalid_repo', err['message'] ?? 'Validation failed', res.statusCode);
    }
  }

  /// Select repository and switch backend engine root.
  Future<SessionData> selectRepo(String repoPath) async {
    final res = await _safePost(
      Uri.parse('$baseUrl/api/repo/select'),
      body: jsonEncode({'repo_path': repoPath}),
    );
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return SessionData.fromJson(data);
    } else {
      final err = jsonDecode(res.body) as Map<String, dynamic>;
      throw ApiException(
          err['error'] ?? 'invalid_repo', err['message'] ?? 'Selection failed', res.statusCode);
    }
  }

  /// Fetch list of recent repositories.
  Future<List<Map<String, dynamic>>> getRecentRepos() async {
    final res = await _safeGet(Uri.parse('$baseUrl/api/repos/recent'));
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return (data['repositories'] as List<dynamic>? ?? [])
          .map((r) => r as Map<String, dynamic>)
          .toList();
    }
    return [];
  }

  /// Reset active session and start a fresh one for the given repository.
  Future<SessionData> resetSession({
    String repoPath = '',
    String intention = 'Review current session changes',
    List<String> criteria = const [],
  }) async {
    final body = jsonEncode({
      if (repoPath.isNotEmpty) 'repo_path': repoPath,
      'intention': intention,
      'criteria': criteria,
    });

    final res = await _safePost(
      Uri.parse('$baseUrl/api/session/reset'),
      body: body,
    );

    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return SessionData.fromJson(data);
    } else {
      final err = jsonDecode(res.body) as Map<String, dynamic>;
      throw ApiException(
          err['error'] ?? 'reset_failed', err['message'] ?? 'Reset failed', res.statusCode);
    }
  }

  /// Query available local Ollama models and offline baseline floor.
  Future<List<ModelOption>> getAvailableModels() async {
    final res = await _safeGet(Uri.parse('$baseUrl/api/models'));
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      final rawList = data['models'] as List<dynamic>? ?? [];
      return rawList
          .map((m) => ModelOption.fromJson(m as Map<String, dynamic>))
          .toList();
    }
    return [];
  }

  /// Execute AI code review against git diff and check receipts.
  Future<ReviewResultData?> requestReview({
    required String repoPath,
    required String intention,
    required List<String> criteria,
    required List<SessionCheckReceipt> receipts,
    List<FindingItem>? priorFindings,
    List<String>? deferrals,
    String? model,
  }) async {
    final requestId = ++_latestRequestId;

    final Map<String, dynamic> bodyMap = {
      'repo_path': repoPath,
      'session_intention': intention,
      'acceptance_criteria': criteria,
      'check_receipts': receipts.map((r) => r.toJson()).toList(),
      'prior_findings': (priorFindings ?? []).map((f) => f.toJson()).toList(),
      'explicit_deferrals': deferrals ?? [],
    };
    if (model != null && model.isNotEmpty) {
      bodyMap['model'] = model;
    }

    final body = jsonEncode(bodyMap);

    final res = await _safePost(
      Uri.parse('$baseUrl/api/review'),
      body: body,
    );

    // C-3: Discard late-arriving responses if another request was triggered
    if (requestId != _latestRequestId) {
      return null;
    }

    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return ReviewResultData.fromJson(data);
    } else if (res.statusCode == 401) {
      throw ApiException('unauthorized', 'Authentication token mismatch', 401);
    } else if (res.statusCode == 403) {
      throw ApiException('forbidden', 'Repository outside boundary', 403);
    } else if (res.statusCode == 409) {
      final errData = jsonDecode(res.body) as Map<String, dynamic>;
      throw ApiException(
          'conflict', errData['message'] as String? ?? 'Snapshot conflict', 409);
    } else if (res.statusCode == 503) {
      throw ApiException('model_unavailable', 'Local Ollama service is unavailable', 503);
    } else {
      throw ApiException('error', 'Review failed with status ${res.statusCode}', res.statusCode);
    }
  }

  /// Poll current chunked review progress.
  Future<ReviewProgressData> getReviewProgress() async {
    final res = await _safeGet(Uri.parse('$baseUrl/api/review/progress'));
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return ReviewProgressData.fromJson(data);
    } else {
      return ReviewProgressData(
        isReviewing: false,
        currentChunk: 0,
        totalChunks: 0,
        currentFiles: '',
        phase: 'idle',
      );
    }
  }

  /// Request cancellation of current review.
  Future<void> cancelCurrentReview() async {
    await _safePost(Uri.parse('$baseUrl/api/review/cancel'));
  }

  /// Fetch active session state from SQLite store.
  Future<SessionData> getActiveSession() async {
    final res = await _safeGet(Uri.parse('$baseUrl/api/session'));
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return SessionData.fromJson(data);
    } else if (res.statusCode == 401) {
      throw ApiException('unauthorized', 'Authentication required', 401);
    } else {
      throw ApiException('error', 'Failed to load session: ${res.statusCode}', res.statusCode);
    }
  }

  /// Update session intention and criteria.
  Future<SessionData> updateSessionIntention({
    required String repoPath,
    required String intention,
    required List<String> criteria,
  }) async {
    final res = await _safePost(
      Uri.parse('$baseUrl/api/session'),
      body: jsonEncode({
        'repo_path': repoPath,
        'intention': intention,
        'criteria': criteria,
      }),
    );
    if (res.statusCode == 200) {
      final data = jsonDecode(res.body) as Map<String, dynamic>;
      return SessionData.fromJson(data);
    } else {
      throw ApiException('error', 'Failed to update intention', res.statusCode);
    }
  }

  /// Update finding lifecycle status and user context note.
  Future<void> updateFindingStatus({
    required String findingId,
    required String status,
    String? userReason,
    String? retiredByReceiptId,
  }) async {
    final res = await _safePatch(
      Uri.parse('$baseUrl/api/findings/$findingId'),
      body: jsonEncode({
        'status': status,
        'user_reason': userReason,
        'retired_by_receipt_id': retiredByReceiptId,
      }),
    );
    if (res.statusCode != 200) {
      throw ApiException('error', 'Failed to update finding status', res.statusCode);
    }
  }

  /// Update restart note and set user edited flag.
  Future<void> updateRestartNote({
    required String repoPath,
    required String restartNote,
    bool isUserEdited = true,
  }) async {
    final res = await _safePost(
      Uri.parse('$baseUrl/api/session/note'),
      body: jsonEncode({
        'repo_path': repoPath,
        'restart_note': restartNote,
        'is_user_edited': isUserEdited,
      }),
    );
    if (res.statusCode != 200) {
      throw ApiException('error', 'Failed to save restart note', res.statusCode);
    }
  }

  /// Finalize and close the current session ('Leave it here').
  Future<void> closeSession({
    required String repoPath,
    Map<String, dynamic>? closingSummary,
  }) async {
    final res = await _safePost(
      Uri.parse('$baseUrl/api/session/close'),
      body: jsonEncode({
        'repo_path': repoPath,
        'closing_summary': closingSummary,
      }),
    );
    if (res.statusCode != 200) {
      throw ApiException('error', 'Failed to close session', res.statusCode);
    }
  }

  /// Trigger clean graceful shutdown of the Python backend.
  Future<void> shutdown() async {
    try {
      await _client.post(
        Uri.parse('$baseUrl/api/shutdown'),
        headers: _authHeaders,
      );
    } catch (_) {}
  }
}
