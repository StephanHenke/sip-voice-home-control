"""Bounded, asynchronous log sinks; no disk fallback or sensitive tracebacks."""
import logging
from logging.handlers import RotatingFileHandler, SysLogHandler
import os
from pathlib import Path
import queue
import socket
import sys
import threading


class SafeFilter(logging.Filter):
    def __init__(self, secrets=()):
        super().__init__()
        self.secrets = [value for value in secrets if value]

    def filter(self, record):
        # HTTP/native internals can contain authorization or SIP payloads.
        if not record.name.startswith('voice_home') and record.levelno < logging.WARNING:
            return False
        if not record.name.startswith('voice_home'):
            message = 'library_event source=' + record.name
        else:
            message = record.getMessage()
        for value in self.secrets:
            message = message.replace(value, '[REDACTED]')
        record.msg, record.args = message, ()
        record.exc_info = record.exc_text = record.stack_info = None
        return True


class RemoteSink(logging.Handler):
    def __init__(self, settings):
        super().__init__()
        self.settings = settings
        self.queue = queue.Queue(maxsize=settings['queue_size'])
        self.dropped = 0
        self.stopped = threading.Event()
        self.worker = threading.Thread(target=self._run, daemon=True)
        self.worker.start()

    def emit(self, record):
        try:
            self.queue.put_nowait(self.format(record))
        except queue.Full:
            self.dropped += 1

    def _run(self):
        sock = None
        while not self.stopped.is_set():
            try:
                message = self.queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                cfg = self.settings
                if sock is None:
                    kind = socket.SOCK_DGRAM if cfg['transport'] == 'udp' else socket.SOCK_STREAM
                    address = socket.getaddrinfo(cfg['host'], cfg['port'], type=kind)[0]
                    sock = socket.socket(address[0], kind)
                    sock.settimeout(1)
                    sock.connect(address[4])
                # RFC3164-compatible PRI; use newline framing for TCP.
                payload = message.encode('utf-8', errors='replace')
                sock.sendall(payload + (b'\n' if cfg['transport'] == 'tcp' else b''))
            except OSError:
                self.dropped += 1
                if sock:
                    sock.close()
                    sock = None
        if sock:
            sock.close()

    def close(self):
        self.stopped.set()
        self.worker.join(timeout=1.2)
        super().close()


class SyslogFormatter(logging.Formatter):
    def __init__(self, facility):
        super().__init__('%(asctime)s voice-home: %(levelname)s %(message)s', datefmt='%b %d %H:%M:%S')
        self.facility = SysLogHandler.facility_names[facility]

    def format(self, record):
        severity = SysLogHandler.priority_names[SysLogHandler.priority_map.get(record.levelname, 'warning')]
        return f'<{self.facility * 8 + severity}>' + super().format(record).replace('\n', ' ')


def configure(settings, secrets=()):
    root = logging.getLogger()
    for handler in root.handlers[:]:
        root.removeHandler(handler)
        handler.close()
    logging.raiseExceptions = False
    off = settings['level'] == 'OFF' or settings['target'] == 'none'
    logging.disable(logging.CRITICAL if off else logging.NOTSET)
    root.setLevel(getattr(logging, settings['level']) if not off else logging.CRITICAL)
    if off:
        root.addHandler(logging.NullHandler())
        return None
    target = settings['target']
    if target == 'file':
        path = Path(settings['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(path, maxBytes=settings['max_bytes'], backupCount=settings['backup_count'], encoding='utf-8')
    elif target == 'syslog':
        handler = RemoteSink(settings)
    else:
        handler = logging.StreamHandler(sys.stderr)
    handler.addFilter(SafeFilter(secrets))
    handler.setFormatter(SyslogFormatter(settings['facility']) if target == 'syslog' else logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    root.addHandler(handler)
    return handler


def suppress_native_output():
    """Preserve Python CLI/log streams while silencing C-level stdout/stderr."""
    for descriptor, name in ((1, 'stdout'), (2, 'stderr')):
        original = getattr(sys, name)
        original.flush()
        saved = os.dup(descriptor)
        setattr(sys, name, os.fdopen(saved, 'w', encoding='utf-8', buffering=1))
        with open(os.devnull, 'wb') as sink:
            os.dup2(sink.fileno(), descriptor)
