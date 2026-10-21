import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'api_client.dart';

class BackendProcessManager {
  Process? _process;
  SteadyDevApiClient? _apiClient;

  SteadyDevApiClient? get apiClient => _apiClient;
  bool get isRunning => _process != null;

  /// Start Python backend process and await handshake readiness line.
  Future<SteadyDevApiClient> startBackend({
    required String repoPath,
    required String backendWorkingDir,
  }) async {
    final completer = Completer<SteadyDevApiClient>();

    try {
      final proc = await Process.start(
        'uv',
        ['run', 'python', '-m', 'steadydev.server', '--repo-path', repoPath],
        workingDirectory: backendWorkingDir,
        environment: {'PYTHONUNBUFFERED': '1'},
        runInShell: false,
        mode: ProcessStartMode.normal,
      );

      _process = proc;

      // Listen for handshake on stdout
      proc.stdout
          .transform(utf8.decoder)
          .transform(const LineSplitter())
          .listen((line) {
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

      // Handle premature process exit
      proc.exitCode.then((code) {
        if (!completer.isCompleted) {
          completer.completeError(
            ApiException('startup_failed', 'Python engine exited with code $code'),
          );
        }
        _process = null;
        _apiClient = null;
      });

      // Handshake timeout after 10 seconds
      return await completer.future.timeout(
        const Duration(seconds: 10),
        onTimeout: () {
          proc.kill();
          throw ApiException('timeout', 'Engine startup timed out waiting for handshake');
        },
      );
    } catch (e) {
      _process?.kill();
      _process = null;
      _apiClient = null;
      rethrow;
    }
  }

  /// Cleanly terminate the backend.
  Future<void> stopBackend() async {
    if (_apiClient != null) {
      await _apiClient!.shutdown();
    }
    if (_process != null) {
      _process!.kill();
      _process = null;
      _apiClient = null;
    }
  }
}
