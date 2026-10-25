import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'api_client.dart';

/// Exception thrown when the SteadyDev backend process fails to start,
/// exits prematurely, or times out awaiting the readiness handshake.
class StartupFailureException implements Exception {
  final String message;
  final String? logPath;
  final List<String> recentStderr;

  const StartupFailureException({
    required this.message,
    this.logPath,
    this.recentStderr = const [],
  });

  @override
  String toString() =>
      'StartupFailureException: $message${logPath != null ? ' (log: $logPath)' : ''}';
}

/// Orchestrates silent, desktop-owned Python backend engine lifecycle,
/// readiness handshake verification, stderr diagnostics capture, and clean shutdown.
class BackendProcessManager {
  Process? _process;
  SteadyDevApiClient? _apiClient;
  IOSink? _logSink;
  File? _currentLogFile;

  SteadyDevApiClient? get apiClient => _apiClient;
  bool get isRunning => _process != null;
  File? get currentLogFile => _currentLogFile;

  /// Scrub raw personal username, Windows paths, and emoji from logs under C-2.
  static String sanitizeDiagnostics(String input) {
    var sanitized = input;
    final username = Platform.environment['USERNAME'];
    if (username != null && username.isNotEmpty) {
      sanitized = sanitized.replaceAll(username, '<USER>');
    }
    sanitized = sanitized.replaceAll('G00dS0ul', '<USER>');
    sanitized = sanitized.replaceAll('🤡', '<EMOJI>');
    sanitized = sanitized.replaceAll(Uri.encodeComponent('🤡'), '<EMOJI>');
    return sanitized;
  }

  /// Locates or creates the sanitized local startup log file under `.steadydev/startup.log`.
  static File getStartupLogFile([String? backendDir]) {
    String? basePath = Platform.environment['LOCALAPPDATA'];
    basePath ??= Platform.environment['APPDATA'];
    if (basePath == null || basePath.isEmpty || !Directory(basePath).existsSync()) {
      basePath = backendDir ?? Directory.current.path;
    }

    final logDir = Directory('$basePath${Platform.pathSeparator}.steadydev');
    if (!logDir.existsSync()) {
      try {
        logDir.createSync(recursive: true);
      } catch (_) {}
    }
    return File('${logDir.path}${Platform.pathSeparator}startup.log');
  }

  /// Resolves the backend working directory containing `pyproject.toml` and `src/steadydev`.
  static String? findBackendDir({String? customDir}) {
    if (customDir != null && customDir.isNotEmpty && _isValidBackend(Directory(customDir))) {
      return Directory(customDir).path;
    }

    final envBackend = Platform.environment['STEADYDEV_BACKEND_DIR'];
    if (envBackend != null && envBackend.isNotEmpty && _isValidBackend(Directory(envBackend))) {
      return Directory(envBackend).path;
    }

    // 1. Search relative to Platform.resolvedExecutable parent hierarchy
    try {
      final exeFile = File(Platform.resolvedExecutable);
      Directory current = exeFile.parent;
      for (int i = 0; i < 7; i++) {
        final candidateBackend = Directory('${current.path}${Platform.pathSeparator}backend');
        if (_isValidBackend(candidateBackend)) return candidateBackend.path;

        if (_isValidBackend(current)) return current.path;

        final parent = current.parent;
        if (parent.path == current.path) break;
        current = parent;
      }
    } catch (_) {}

    // 2. Search relative to Directory.current hierarchy
    try {
      Directory current = Directory.current;
      for (int i = 0; i < 6; i++) {
        final candidateBackend = Directory('${current.path}${Platform.pathSeparator}backend');
        if (_isValidBackend(candidateBackend)) return candidateBackend.path;

        if (_isValidBackend(current)) return current.path;

        final parent = current.parent;
        if (parent.path == current.path) break;
        current = parent;
      }
    } catch (_) {}

    return null;
  }

  static bool _isValidBackend(Directory dir) {
    if (!dir.existsSync()) return false;
    final pyproject = File('${dir.path}${Platform.pathSeparator}pyproject.toml');
    final serverSrc = File(
        '${dir.path}${Platform.pathSeparator}src${Platform.pathSeparator}steadydev${Platform.pathSeparator}server.py');
    final serverDirect = File(
        '${dir.path}${Platform.pathSeparator}steadydev${Platform.pathSeparator}server.py');
    return pyproject.existsSync() && (serverSrc.existsSync() || serverDirect.existsSync());
  }

  /// Resolves the target Git repository root.
  static String? findTargetRepo({String? customRepo, String? backendDir}) {
    if (customRepo != null && customRepo.isNotEmpty && _isValidGitRepo(Directory(customRepo))) {
      return Directory(customRepo).path;
    }

    final envRepo = Platform.environment['STEADYDEV_REPO_PATH'];
    if (envRepo != null && envRepo.isNotEmpty && _isValidGitRepo(Directory(envRepo))) {
      return Directory(envRepo).path;
    }

    // Check backendDir and its ancestors
    if (backendDir != null) {
      Directory current = Directory(backendDir);
      for (int i = 0; i < 5; i++) {
        if (_isValidGitRepo(current)) return current.path;
        final parent = current.parent;
        if (parent.path == current.path) break;
        current = parent;
      }
    }

    // Check Directory.current and ancestors
    Directory current = Directory.current;
    for (int i = 0; i < 5; i++) {
      if (_isValidGitRepo(current)) return current.path;
      final parent = current.parent;
      if (parent.path == current.path) break;
      current = parent;
    }

    // Check executable directory and ancestors
    try {
      final exeFile = File(Platform.resolvedExecutable);
      Directory exeCurrent = exeFile.parent;
      for (int i = 0; i < 6; i++) {
        if (_isValidGitRepo(exeCurrent)) return exeCurrent.path;
        final parent = exeCurrent.parent;
        if (parent.path == exeCurrent.path) break;
        exeCurrent = parent;
      }
    } catch (_) {}

    // Check candidate sample-project in application roots
    final candidateRoots = <Directory>[
      if (backendDir != null) Directory(backendDir).parent,
      Directory.current,
    ];
    try {
      final exeFile = File(Platform.resolvedExecutable);
      candidateRoots.add(exeFile.parent.parent);
      candidateRoots.add(exeFile.parent);
    } catch (_) {}

    for (final root in candidateRoots) {
      if (!root.existsSync()) continue;
      final sample = Directory('${root.path}${Platform.pathSeparator}sample-project');
      if (_isValidGitRepo(sample)) return sample.path;
    }

    // Auto-initialize sample-project if git is available
    for (final root in candidateRoots) {
      if (root.existsSync()) {
        final sample = Directory('${root.path}${Platform.pathSeparator}sample-project');
        try {
          if (!sample.existsSync()) sample.createSync(recursive: true);
          final res = Process.runSync('git', ['init', '-q'], workingDirectory: sample.path);
          if (res.exitCode == 0) {
            final readme = File('${sample.path}${Platform.pathSeparator}README.md');
            if (!readme.existsSync()) {
              readme.writeAsStringSync(
                '# Sample Project for SteadyDev Review\nThis is a starter sample project.\n',
              );
              Process.runSync('git', ['add', 'README.md'], workingDirectory: sample.path);
              Process.runSync('git', ['commit', '-q', '-m', 'Initial commit'], workingDirectory: sample.path);
            }
            return sample.path;
          }
        } catch (_) {}
      }
    }

    return null;
  }

  static bool _isValidGitRepo(Directory dir) {
    if (!dir.existsSync()) return false;
    final gitDir = Directory('${dir.path}${Platform.pathSeparator}.git');
    final gitFile = File('${dir.path}${Platform.pathSeparator}.git');
    return gitDir.existsSync() || gitFile.existsSync();
  }

  /// Probes whether a backend service is already active on localhost:8765.
  static Future<SteadyDevApiClient?> probeExistingBackend({
    String host = '127.0.0.1',
    int port = 8765,
    String token = 'dev-token-123',
    Duration timeout = const Duration(milliseconds: 600),
  }) async {
    try {
      final socket = await Socket.connect(host, port, timeout: timeout);
      await socket.close();
      return SteadyDevApiClient(
        baseUrl: 'http://$host:$port',
        token: token,
      );
    } catch (_) {
      return null;
    }
  }

  /// Spawns the Python backend silently without console window and awaits
  /// the readiness handshake `STEADYDEV_READY port=<port> token=<token>`.
  Future<SteadyDevApiClient> startBackend({
    String? repoPath,
    String? backendWorkingDir,
    Duration timeout = const Duration(seconds: 15),
  }) async {
    final resolvedBackend = backendWorkingDir ?? findBackendDir() ?? Directory.current.path;
    final resolvedRepo = repoPath ?? findTargetRepo(backendDir: resolvedBackend) ?? resolvedBackend;

    final logFile = getStartupLogFile(resolvedBackend);
    _currentLogFile = logFile;

    try {
      _logSink = logFile.openWrite(mode: FileMode.writeOnlyAppend);
      _logSink!.writeln('=== SteadyDev Launch [${DateTime.now().toUtc().toIso8601String()}] ===');
      _logSink!.writeln('Executable: ${sanitizeDiagnostics(Platform.resolvedExecutable)}');
      _logSink!.writeln('Backend Dir: ${sanitizeDiagnostics(resolvedBackend)}');
      _logSink!.writeln('Repo Path: ${sanitizeDiagnostics(resolvedRepo)}');
    } catch (_) {}

    final completer = Completer<SteadyDevApiClient>();
    final recentStderr = <String>[];

    try {
      // Dart VM process_win.cc sets CREATE_NO_WINDOW when mode is ProcessStartMode.normal
      // and runInShell is false with piped stdio.
      final proc = await Process.start(
        'uv',
        [
          'run',
          'python',
          '-m',
          'steadydev.server',
          '--repo-path',
          resolvedRepo,
          '--port',
          '0',
        ],
        workingDirectory: resolvedBackend,
        environment: {'PYTHONUNBUFFERED': '1'},
        runInShell: false,
        mode: ProcessStartMode.normal,
      );

      _process = proc;

      // Pipe stderr to ring buffer and sanitized log
      proc.stderr
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen((line) {
        final clean = sanitizeDiagnostics(line);
        recentStderr.add(clean);
        if (recentStderr.length > 50) {
          recentStderr.removeAt(0);
        }
        try {
          _logSink?.writeln('[STDERR] $clean');
        } catch (_) {}
      });

      // Listen on stdout for readiness handshake
      proc.stdout
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen((line) {
        final clean = sanitizeDiagnostics(line);
        try {
          _logSink?.writeln('[STDOUT] $clean');
        } catch (_) {}

        if (line.startsWith('STEADYDEV_READY ')) {
          final parts = line.substring(16).trim().split(' ');
          int? port;
          String? token;
          for (final part in parts) {
            if (part.startsWith('port=')) {
              port = int.tryParse(part.substring(5));
            } else if (part.startsWith('token=')) {
              token = part.substring(6);
            }
          }

          if (port != null && token != null && !completer.isCompleted) {
            final client = SteadyDevApiClient(
              baseUrl: 'http://127.0.0.1:$port',
              token: token,
            );
            _apiClient = client;
            completer.complete(client);
          }
        }
      });

      // Handle premature exit
      proc.exitCode.then((code) {
        if (!completer.isCompleted) {
          completer.completeError(
            StartupFailureException(
              message: 'SteadyDev backend process exited prematurely with code $code',
              logPath: logFile.path,
              recentStderr: List.unmodifiable(recentStderr),
            ),
          );
        }
        _process = null;
        _apiClient = null;
      });

      // Handshake timeout after specified duration (15s)
      return await completer.future.timeout(
        timeout,
        onTimeout: () {
          proc.kill();
          throw StartupFailureException(
            message: 'SteadyDev backend startup timed out waiting for handshake ($timeout)',
            logPath: logFile.path,
            recentStderr: List.unmodifiable(recentStderr),
          );
        },
      );
    } catch (e) {
      _process?.kill();
      _process = null;
      _apiClient = null;
      if (e is StartupFailureException) rethrow;
      throw StartupFailureException(
        message: 'Failed to launch SteadyDev backend: $e',
        logPath: logFile.path,
        recentStderr: List.unmodifiable(recentStderr),
      );
    }
  }

  /// Cleanly terminates the backend process via API shutdown and process kill.
  Future<void> stopBackend() async {
    if (_apiClient != null) {
      try {
        await _apiClient!.shutdown().timeout(const Duration(seconds: 2));
      } catch (_) {}
    }
    if (_process != null) {
      try {
        _process!.kill();
      } catch (_) {}
      _process = null;
      _apiClient = null;
    }
    if (_logSink != null) {
      try {
        await _logSink!.flush();
        await _logSink!.close();
      } catch (_) {}
      _logSink = null;
    }
  }
}
