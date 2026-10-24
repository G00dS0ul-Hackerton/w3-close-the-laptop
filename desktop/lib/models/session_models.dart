enum FindingType {
  confirmed,
  unverified,
  needsJudgment,
}

enum FindingLifecycle {
  open,
  deferred,
  resolved,
  dismissed,
  evidenceRetired,
}

class FindingItem {
  final String id;
  final String title;
  final String description;
  final String locator;
  final FindingType type;
  FindingLifecycle lifecycle;
  final String? receiptSnippet;
  final String? limit;
  String? reason;
  final bool isStale;
  final String? staleReason;
  final String? retiredByReceiptId;
  final String engine;

  FindingItem({
    required this.id,
    required this.title,
    required this.description,
    required this.locator,
    required this.type,
    this.lifecycle = FindingLifecycle.open,
    this.receiptSnippet,
    this.limit,
    this.reason,
    this.isStale = false,
    this.staleReason,
    this.retiredByReceiptId,
    this.engine = 'baseline-checklist',
  });

  factory FindingItem.fromJson(Map<String, dynamic> json) {
    final cat = (json['category'] as String? ?? 'evidence_mismatch').toLowerCase();
    FindingType fType;
    if (cat.contains('unverified')) {
      fType = FindingType.unverified;
    } else if (cat.contains('judgment') || cat.contains('uncertainty')) {
      fType = FindingType.needsJudgment;
    } else {
      fType = FindingType.confirmed;
    }

    final stat = (json['status'] as String? ?? 'open').toLowerCase().replaceAll('_', '-');
    FindingLifecycle life;
    if (stat == 'deferred') {
      life = FindingLifecycle.deferred;
    } else if (stat == 'resolved' || stat == 'user-reported-resolved') {
      life = FindingLifecycle.resolved;
    } else if (stat == 'dismissed') {
      life = FindingLifecycle.dismissed;
    } else if (stat == 'evidence-retired' || stat.contains('retire')) {
      life = FindingLifecycle.evidenceRetired;
    } else {
      life = FindingLifecycle.open;
    }

    final isStaleVal = json['is_stale'];
    final bool isStaleBool = isStaleVal is bool ? isStaleVal : (isStaleVal == 1);

    final String rawDesc = json['description'] as String? ?? 'Unrecorded check';
    final String rawEvidence = json['evidence'] as String? ?? (json['detail'] as String? ?? '');
    final String titleStr = json['title'] as String? ?? rawDesc;
    String descStr = rawEvidence.isNotEmpty ? rawEvidence : rawDesc;
    if (descStr == titleStr) {
      descStr = 'No passing check receipt attached for this modification in the current snapshot.';
    }

    return FindingItem(
      id: json['finding_id'] as String? ?? (json['id'] as String? ?? 'f-${DateTime.now().millisecondsSinceEpoch}'),
      title: titleStr,
      description: descStr,
      locator: json['locator'] as String? ?? (json['file_path'] as String? ?? 'repository'),
      type: fType,
      lifecycle: life,
      receiptSnippet: json['receipt_excerpt'] as String? ?? (rawEvidence.isNotEmpty ? rawEvidence : null),
      limit: json['limitations'] as String? ??
          'This is an evidence gap, not a confirmed bug. You may have verified it outside this tool.',
      reason: json['user_reason'] as String?,
      isStale: isStaleBool,
      staleReason: json['stale_reason'] as String?,
      retiredByReceiptId: json['retired_by_receipt_id'] as String?,
      engine: json['engine'] as String? ?? 'baseline-checklist',
    );
  }

  String get categoryString {
    switch (type) {
      case FindingType.confirmed:
        return 'evidence_mismatch';
      case FindingType.unverified:
        return 'unverified';
      case FindingType.needsJudgment:
        return 'needs_judgment';
    }
  }

  String get statusString {
    switch (lifecycle) {
      case FindingLifecycle.open:
        return 'open';
      case FindingLifecycle.deferred:
        return 'deferred';
      case FindingLifecycle.resolved:
        return 'user-reported-resolved';
      case FindingLifecycle.dismissed:
        return 'dismissed';
      case FindingLifecycle.evidenceRetired:
        return 'evidence-retired';
    }
  }

  Map<String, dynamic> toJson() => {
        'finding_id': id,
        'category': categoryString,
        'description': description,
        'locator': locator,
        'status': statusString,
        'receipt_excerpt': receiptSnippet,
        'limitations': limit,
        'user_reason': reason,
        'is_stale': isStale ? 1 : 0,
        'stale_reason': staleReason,
        'retired_by_receipt_id': retiredByReceiptId,
      };
}

class SessionCheckReceipt {
  final String id;
  final String command;
  final int exitCode;
  final String output;
  final String timestampUtc;

  SessionCheckReceipt({
    required this.id,
    required this.command,
    required this.exitCode,
    required this.output,
    required this.timestampUtc,
  });

  factory SessionCheckReceipt.fromJson(Map<String, dynamic> json) => SessionCheckReceipt(
        id: json['receipt_id'] as String? ?? '',
        command: json['command'] as String? ?? '',
        exitCode: json['exit_code'] as int? ?? 0,
        output: json['output_summary'] as String? ?? '',
        timestampUtc: json['timestamp_utc'] as String? ?? '',
      );

  Map<String, dynamic> toJson() => {
        'receipt_id': id,
        'command': command,
        'exit_code': exitCode,
        'output_summary': output,
        'timestamp_utc': timestampUtc,
      };
}

class ModelOption {
  final String id;
  final String name;
  final String displayName;
  final String family;
  final String parameterSize;
  final String quantization;
  final int sizeBytes;
  final bool isRunning;
  final bool isRecommended;
  final bool isBaseline;

  const ModelOption({
    required this.id,
    required this.name,
    required this.displayName,
    this.family = '',
    this.parameterSize = '',
    this.quantization = '',
    this.sizeBytes = 0,
    this.isRunning = false,
    this.isRecommended = false,
    this.isBaseline = false,
  });

  factory ModelOption.fromJson(Map<String, dynamic> json) {
    return ModelOption(
      id: json['id'] as String? ?? json['name'] as String? ?? '',
      name: json['name'] as String? ?? json['id'] as String? ?? '',
      displayName: json['display_name'] as String? ?? json['name'] as String? ?? 'Unknown',
      family: json['family'] as String? ?? '',
      parameterSize: json['parameter_size'] as String? ?? '',
      quantization: json['quantization'] as String? ?? '',
      sizeBytes: (json['size_bytes'] as num? ?? 0).toInt(),
      isRunning: json['is_running'] as bool? ?? false,
      isRecommended: json['is_recommended'] as bool? ?? false,
      isBaseline: json['is_baseline'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() => {
        'id': id,
        'name': name,
        'display_name': displayName,
        'family': family,
        'parameter_size': parameterSize,
        'quantization': quantization,
        'size_bytes': sizeBytes,
        'is_running': isRunning,
        'is_recommended': isRecommended,
        'is_baseline': isBaseline,
      };
}

class ModelAttemptData {
  final String model;
  final String outcome;
  final double durationMs;
  final int? inputTokens;
  final int? outputTokens;
  final String? doneReason;
  final String? errorDetail;

  ModelAttemptData({
    required this.model,
    required this.outcome,
    this.durationMs = 0.0,
    this.inputTokens,
    this.outputTokens,
    this.doneReason,
    this.errorDetail,
  });

  factory ModelAttemptData.fromJson(Map<String, dynamic> json) {
    return ModelAttemptData(
      model: json['model'] as String? ?? 'unknown',
      outcome: json['outcome'] as String? ?? 'unknown',
      durationMs: (json['duration_ms'] as num? ?? 0.0).toDouble(),
      inputTokens: json['input_tokens'] as int?,
      outputTokens: json['output_tokens'] as int?,
      doneReason: json['done_reason'] as String?,
      errorDetail: json['error_detail'] as String?,
    );
  }
}

class ChunkProvenanceData {
  final int chunkIndex;
  final int totalChunks;
  final List<String> filePaths;
  final List<ModelAttemptData> attempts;
  final String resolvedEngine;
  final String? fallbackReason;
  final int findingsCount;

  ChunkProvenanceData({
    required this.chunkIndex,
    required this.totalChunks,
    required this.filePaths,
    required this.attempts,
    required this.resolvedEngine,
    this.fallbackReason,
    this.findingsCount = 0,
  });

  factory ChunkProvenanceData.fromJson(Map<String, dynamic> json) {
    final rawAttempts = json['attempts'] as List<dynamic>? ?? [];
    final rawFiles = json['file_paths'] as List<dynamic>? ?? [];
    return ChunkProvenanceData(
      chunkIndex: json['chunk_index'] as int? ?? 1,
      totalChunks: json['total_chunks'] as int? ?? 1,
      filePaths: rawFiles.map((e) => e.toString()).toList(),
      attempts: rawAttempts
          .map((a) => ModelAttemptData.fromJson(a as Map<String, dynamic>))
          .toList(),
      resolvedEngine: json['resolved_engine'] as String? ?? 'baseline-checklist',
      fallbackReason: json['fallback_reason'] as String?,
      findingsCount: json['findings_count'] as int? ?? 0,
    );
  }
}

class ReviewResultData {
  final String packetId;
  final String modelTag;
  final double elapsedSeconds;
  final String status;
  final List<FindingItem> findings;
  final String closingSummary;
  final String restartNote;
  final List<String> retiredFindingIds;
  final String? error;
  final bool unchangedSnapshot;
  final List<ChunkProvenanceData> chunkProvenance;

  ReviewResultData({
    required this.packetId,
    required this.modelTag,
    required this.elapsedSeconds,
    required this.status,
    required this.findings,
    required this.closingSummary,
    required this.restartNote,
    required this.retiredFindingIds,
    this.error,
    this.unchangedSnapshot = false,
    this.chunkProvenance = const [],
  });

  bool get isFallback =>
      status == 'fallback_baseline' ||
      (error != null && error!.toLowerCase().contains('fell back'));

  bool get isPartialCoverage {
    if (chunkProvenance.isEmpty) return false;
    final hasBaseline =
        chunkProvenance.any((c) => c.resolvedEngine.contains('baseline'));
    final hasAi =
        chunkProvenance.any((c) => !c.resolvedEngine.contains('baseline'));
    return hasBaseline && hasAi;
  }

  int get aiChunksCount =>
      chunkProvenance.where((c) => !c.resolvedEngine.contains('baseline')).length;

  int get baselineChunksCount =>
      chunkProvenance.where((c) => c.resolvedEngine.contains('baseline')).length;

  factory ReviewResultData.fromJson(Map<String, dynamic> json) {
    final rawFindings = json['findings'] as List<dynamic>? ?? [];
    final rawProvenance = json['chunk_provenance'] as List<dynamic>? ?? [];
    return ReviewResultData(
      packetId: json['packet_id'] as String? ?? '',
      modelTag: json['model_name'] as String? ??
          json['model_tag'] as String? ??
          'gemma3:4b',
      elapsedSeconds: (json['elapsed_seconds'] as num? ?? 0.0).toDouble(),
      status: json['status'] as String? ?? 'clean',
      findings: rawFindings
          .map((f) => FindingItem.fromJson(f as Map<String, dynamic>))
          .toList(),
      closingSummary: json['closing_summary'] as String? ?? '',
      restartNote: json['restart_note'] as String? ?? '',
      retiredFindingIds: (json['retired_finding_ids'] as List<dynamic>? ?? [])
          .map((e) => e.toString())
          .toList(),
      error: json['error'] as String?,
      unchangedSnapshot: json['unchanged_snapshot'] as bool? ?? false,
      chunkProvenance: rawProvenance
          .map((p) => ChunkProvenanceData.fromJson(p as Map<String, dynamic>))
          .toList(),
    );
  }
}

class ReviewDiagnosticsData {
  final String reviewId;
  final String phase;
  final bool isReviewing;
  final String repoName;
  final String? snapshotHash;
  final int totalFiles;
  final int totalChunks;
  final int currentChunk;
  final List<String> currentFiles;
  final List<ChunkProvenanceData> chunkDiagnostics;
  final double elapsedMs;
  final double? deadlineSeconds;
  final bool deadlineExceeded;
  final String status;
  final String? error;
  final String createdAt;
  final String updatedAt;

  ReviewDiagnosticsData({
    required this.reviewId,
    required this.phase,
    required this.isReviewing,
    required this.repoName,
    this.snapshotHash,
    required this.totalFiles,
    required this.totalChunks,
    required this.currentChunk,
    required this.currentFiles,
    required this.chunkDiagnostics,
    required this.elapsedMs,
    this.deadlineSeconds,
    required this.deadlineExceeded,
    required this.status,
    this.error,
    required this.createdAt,
    required this.updatedAt,
  });

  factory ReviewDiagnosticsData.fromJson(Map<String, dynamic> json) {
    final rawChunks = json['chunk_diagnostics'] as List<dynamic>? ?? [];
    final rawFiles = json['current_files'] as List<dynamic>? ?? [];
    return ReviewDiagnosticsData(
      reviewId: json['review_id'] as String? ?? 'idle',
      phase: json['phase'] as String? ?? 'idle',
      isReviewing: json['is_reviewing'] as bool? ?? false,
      repoName: json['repo_name'] as String? ?? '',
      snapshotHash: json['snapshot_hash'] as String?,
      totalFiles: json['total_files'] as int? ?? 0,
      totalChunks: json['total_chunks'] as int? ?? 0,
      currentChunk: json['current_chunk'] as int? ?? 0,
      currentFiles: rawFiles.map((e) => e.toString()).toList(),
      chunkDiagnostics: rawChunks
          .map((c) => ChunkProvenanceData.fromJson(c as Map<String, dynamic>))
          .toList(),
      elapsedMs: (json['elapsed_ms'] as num? ?? 0.0).toDouble(),
      deadlineSeconds: json.containsKey('deadline_seconds')
          ? (json['deadline_seconds'] as num?)?.toDouble()
          : 180.0,
      deadlineExceeded: json['deadline_exceeded'] as bool? ?? false,
      status: json['status'] as String? ?? 'idle',
      error: json['error'] as String?,
      createdAt: json['created_at'] as String? ?? '',
      updatedAt: json['updated_at'] as String? ?? '',
    );
  }
}

class ReviewExecutionConfig {
  final String modelId;
  /// Workflow timeout in seconds, or `null` for Unlimited (no timeout).
  final double? workflowTimeoutSeconds;
  /// Fallback behavior when primary model times out or fails:
  /// - `'secondary_model'`: fall back to paired secondary AI model (no baseline floor)
  /// - `'baseline_only'`: fall back directly to deterministic checklist baseline
  /// - `'no_fallback'`: do not fall back (primary AI model only)
  final String fallbackPolicy;

  const ReviewExecutionConfig({
    required this.modelId,
    this.workflowTimeoutSeconds = 300.0,
    this.fallbackPolicy = 'secondary_model',
  });

  bool get isUnlimitedTimeout =>
      workflowTimeoutSeconds == null || workflowTimeoutSeconds! <= 0;

  String? get resolvedFallbackModel {
    if (modelId == 'baseline-checklist') return null;
    if (fallbackPolicy != 'secondary_model') return null;
    if (modelId.contains('qwen')) return 'gemma3:4b';
    return 'qwen2.5-coder:3b';
  }

  bool get useBaselineFallback {
    if (modelId == 'baseline-checklist') return true;
    return fallbackPolicy == 'baseline_only';
  }

  String get timeoutSummaryLabel {
    if (isUnlimitedTimeout) return 'Unlimited';
    return '${workflowTimeoutSeconds!.toInt()}s';
  }

  String get fallbackSummaryLabel {
    if (modelId == 'baseline-checklist') return 'Baseline';
    switch (fallbackPolicy) {
      case 'secondary_model':
        return resolvedFallbackModel?.contains('gemma') == true
            ? 'Fallback: Gemma 3'
            : 'Fallback: Qwen 2.5';
      case 'baseline_only':
        return 'Fallback: Baseline';
      case 'no_fallback':
      default:
        return 'No Fallback';
    }
  }
}

class GitStateSummary {
  final String state; // 'clean' | 'dirty' | 'no_commits' | 'all_omitted'
  final bool hasCommits;
  final String headSha;
  final String branch;
  final int changedFilesCount;
  final int omittedFilesCount;

  GitStateSummary({
    required this.state,
    required this.hasCommits,
    required this.headSha,
    required this.branch,
    required this.changedFilesCount,
    required this.omittedFilesCount,
  });

  factory GitStateSummary.fromJson(Map<String, dynamic> json) {
    return GitStateSummary(
      state: json['state'] as String? ?? 'clean',
      hasCommits: json['has_commits'] as bool? ?? false,
      headSha: json['head_sha'] as String? ?? '',
      branch: json['branch'] as String? ?? '',
      changedFilesCount: json['changed_files_count'] as int? ?? 0,
      omittedFilesCount: json['omitted_files_count'] as int? ?? 0,
    );
  }
}

class SessionData {
  final String sessionId;
  final String repoPath;
  final String repoName;
  final String intention;
  final List<String> criteria;
  final String restartNote;
  final bool isNoteUserEdited;
  final bool isEnded;
  final List<FindingItem> findings;
  final List<SessionCheckReceipt> checkReceipts;
  final GitStateSummary? gitStatus;

  SessionData({
    required this.sessionId,
    required this.repoPath,
    required this.repoName,
    required this.intention,
    required this.criteria,
    required this.restartNote,
    required this.isNoteUserEdited,
    required this.isEnded,
    required this.findings,
    required this.checkReceipts,
    this.gitStatus,
  });

  factory SessionData.fromJson(Map<String, dynamic> json) {
    final rawFindings = json['findings'] as List<dynamic>? ?? [];
    final rawReceipts = json['check_receipts'] as List<dynamic>? ?? [];
    final rawCriteria = json['criteria'] as List<dynamic>? ?? [];
    final noteEditedVal = json['is_note_user_edited'];
    final bool noteEditedBool =
        noteEditedVal is bool ? noteEditedVal : (noteEditedVal == 1);
    final isEndedVal = json['is_ended'];
    final bool isEndedBool = isEndedVal is bool ? isEndedVal : (isEndedVal == 1);

    return SessionData(
      sessionId: json['session_id'] as String? ?? '',
      repoPath: json['repo_path'] as String? ?? '',
      repoName: json['repo_name'] as String? ?? '',
      intention: json['intention'] as String? ?? '',
      criteria: rawCriteria.map((c) => c.toString()).toList(),
      restartNote: json['restart_note'] as String? ?? '',
      isNoteUserEdited: noteEditedBool,
      isEnded: isEndedBool,
      findings: rawFindings
          .map((f) => FindingItem.fromJson(f as Map<String, dynamic>))
          .toList(),
      checkReceipts: rawReceipts
          .map((r) => SessionCheckReceipt.fromJson(r as Map<String, dynamic>))
          .toList(),
      gitStatus: json['git_status'] != null
          ? GitStateSummary.fromJson(json['git_status'] as Map<String, dynamic>)
          : null,
    );
  }
}

class ReviewProgressData {
  final bool isReviewing;
  final int currentChunk;
  final int totalChunks;
  final String currentFiles;
  final String phase;

  ReviewProgressData({
    required this.isReviewing,
    required this.currentChunk,
    required this.totalChunks,
    required this.currentFiles,
    required this.phase,
  });

  factory ReviewProgressData.fromJson(Map<String, dynamic> json) {
    return ReviewProgressData(
      isReviewing: json['is_reviewing'] as bool? ?? false,
      currentChunk: json['current_chunk'] as int? ?? 0,
      totalChunks: json['total_chunks'] as int? ?? 0,
      currentFiles: json['current_files'] as String? ?? '',
      phase: json['phase'] as String? ?? 'idle',
    );
  }
}

class TelemetryDeliveryReceiptData {
  final String? traceId;
  final String state;
  final String? timestampUtc;
  final bool verifiedDelivery;
  final String? errorDetail;

  TelemetryDeliveryReceiptData({
    this.traceId,
    required this.state,
    this.timestampUtc,
    required this.verifiedDelivery,
    this.errorDetail,
  });

  factory TelemetryDeliveryReceiptData.fromJson(Map<String, dynamic> json) {
    return TelemetryDeliveryReceiptData(
      traceId: json['trace_id'] as String?,
      state: json['state'] as String? ?? 'disabled',
      timestampUtc: json['timestamp_utc'] as String?,
      verifiedDelivery: json['verified_delivery'] as bool? ?? false,
      errorDetail: json['error_detail'] as String?,
    );
  }
}

class TelemetryConfigData {
  final bool enabled;
  final bool dsnConfigured;
  final String maskedDsn;
  final String exportState;
  final String? lastTraceId;
  final String? traceUrl;
  final bool verifiedDelivery;
  final bool effectiveImmediately;
  final bool pendingActivation;
  final TelemetryDeliveryReceiptData? deliveryReceipt;
  final bool isReviewing;

  TelemetryConfigData({
    required this.enabled,
    required this.dsnConfigured,
    required this.maskedDsn,
    required this.exportState,
    this.lastTraceId,
    this.traceUrl,
    required this.verifiedDelivery,
    this.effectiveImmediately = true,
    this.pendingActivation = false,
    this.deliveryReceipt,
    this.isReviewing = false,
  });

  factory TelemetryConfigData.fromJson(Map<String, dynamic> json) {
    final rawReceipt = json['delivery_receipt'] as Map<String, dynamic>?;
    return TelemetryConfigData(
      enabled: json['enabled'] as bool? ?? false,
      dsnConfigured: json['dsn_configured'] as bool? ?? false,
      maskedDsn: json['masked_dsn'] as String? ?? '',
      exportState: json['export_state'] as String? ?? 'disabled',
      lastTraceId: json['last_trace_id'] as String?,
      traceUrl: json['trace_url'] as String?,
      verifiedDelivery: json['verified_delivery'] as bool? ?? false,
      effectiveImmediately: json['effective_immediately'] as bool? ?? true,
      pendingActivation: json['pending_activation'] as bool? ?? false,
      deliveryReceipt: rawReceipt != null
          ? TelemetryDeliveryReceiptData.fromJson(rawReceipt)
          : null,
      isReviewing: json['is_reviewing'] as bool? ?? false,
    );
  }
}
