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

    final stat = json['status'] as String? ?? 'open';
    FindingLifecycle life;
    switch (stat) {
      case 'deferred':
        life = FindingLifecycle.deferred;
        break;
      case 'resolved':
        life = FindingLifecycle.resolved;
        break;
      case 'dismissed':
        life = FindingLifecycle.dismissed;
        break;
      default:
        life = FindingLifecycle.open;
        break;
    }

    return FindingItem(
      id: json['finding_id'] as String? ?? 'f-${DateTime.now().millisecondsSinceEpoch}',
      title: json['description'] as String? ?? 'Unrecorded check',
      description: json['description'] as String? ?? '',
      locator: json['locator'] as String? ?? 'repository',
      type: fType,
      lifecycle: life,
      receiptSnippet: json['receipt_excerpt'] as String?,
      limit: json['limitations'] as String?,
      reason: json['user_reason'] as String?,
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

class ReviewResultData {
  final String packetId;
  final String modelTag;
  final double elapsedSeconds;
  final String status;
  final List<FindingItem> findings;
  final String closingSummary;
  final String restartNote;
  final List<String> retiredFindingIds;

  ReviewResultData({
    required this.packetId,
    required this.modelTag,
    required this.elapsedSeconds,
    required this.status,
    required this.findings,
    required this.closingSummary,
    required this.restartNote,
    required this.retiredFindingIds,
  });

  factory ReviewResultData.fromJson(Map<String, dynamic> json) {
    final rawFindings = json['findings'] as List<dynamic>? ?? [];
    return ReviewResultData(
      packetId: json['packet_id'] as String? ?? '',
      modelTag: json['model_tag'] as String? ?? 'qwen2.5-coder:3b',
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
    );
  }
}
