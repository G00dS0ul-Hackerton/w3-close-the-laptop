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
  });

  bool get isFallback =>
      status == 'fallback_baseline' ||
      (error != null && error!.toLowerCase().contains('fell back'));

  factory ReviewResultData.fromJson(Map<String, dynamic> json) {
    final rawFindings = json['findings'] as List<dynamic>? ?? [];
    return ReviewResultData(
      packetId: json['packet_id'] as String? ?? '',
      modelTag: json['model_name'] as String? ?? json['model_tag'] as String? ?? 'gemma3:4b',
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
    );
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
