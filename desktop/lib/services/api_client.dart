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

  /// Check engine health and Ollama model status.
  Future<Map<String, dynamic>> checkHealth() async {
    try {
      final res = await _client.get(
        Uri.parse('$baseUrl/api/health'),
        headers: _authHeaders,
      );
      if (res.statusCode == 200) {
        return jsonDecode(res.body) as Map<String, dynamic>;
      } else if (res.statusCode == 401) {
        throw ApiException('unauthorized', 'Authentication required', 401);
      } else {
        throw ApiException('error', 'Health check failed: ${res.statusCode}', res.statusCode);
      }
    } catch (e) {
      if (e is ApiException) rethrow;
      throw ApiException('engine_offline', 'Cannot reach local engine at $baseUrl: $e');
    }
  }

  /// Request snapshot summary from git collector.
  Future<Map<String, dynamic>> getSnapshot(String repoPath) async {
    final res = await _client.post(
      Uri.parse('$baseUrl/api/snapshot'),
      headers: _authHeaders,
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

  /// Execute AI code review against git diff and check receipts.
  Future<ReviewResultData?> requestReview({
    required String repoPath,
    required String intention,
    required List<String> criteria,
    required List<SessionCheckReceipt> receipts,
    List<FindingItem>? priorFindings,
    List<String>? deferrals,
  }) async {
    final requestId = ++_latestRequestId;

    final body = jsonEncode({
      'repo_path': repoPath,
      'session_intention': intention,
      'acceptance_criteria': criteria,
      'check_receipts': receipts.map((r) => r.toJson()).toList(),
      'prior_findings': (priorFindings ?? []).map((f) => f.toJson()).toList(),
      'explicit_deferrals': deferrals ?? [],
    });

    final res = await _client.post(
      Uri.parse('$baseUrl/api/review'),
      headers: _authHeaders,
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
    } else if (res.statusCode == 503) {
      throw ApiException('model_unavailable', 'Local Ollama service is unavailable', 503);
    } else {
      throw ApiException('error', 'Review failed with status ${res.statusCode}', res.statusCode);
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
