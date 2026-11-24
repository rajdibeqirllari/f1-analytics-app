"""Record F1 live timing to a file without an F1 TV login.

FastF1 3.8.3 passes access_token_factory=None when no_auth=True, which signalrcore rejects
("access_token_factory is not function"). This drops that option so the connection is made
without a token. Usage:
    .\\.venv\\Scripts\\python.exe scripts\\record_live.py tmp\\mexico_q_live.txt
"""
import sys

import signalrcore.hub_connection_builder as hub

_with_url = hub.HubConnectionBuilder.with_url


def _with_url_no_token(self, url, options=None):
    if options is not None and options.get('access_token_factory') is None:
        options = {k: v for k, v in options.items() if k != 'access_token_factory'}
    return _with_url(self, url, options)


hub.HubConnectionBuilder.with_url = _with_url_no_token

# signalrcore 1.0.1 reads each WebSocket frame with a single sock.recv(), which over TLS returns at
# most a few KB, and ignores continuation frames. F1's first message is much bigger, so it arrived cut
# off at 4096 characters. Read frames fully and join fragments (same approach as signalrcore 1.0.2).
import ssl  # noqa: E402
import struct  # noqa: E402
from signalrcore.transport.websockets import websocket_client as _wc  # noqa: E402
from signalrcore.transport.sockets.errors import NoHeaderException, SocketClosedError  # noqa: E402


def _recv_exactly(sock, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            raise SocketClosedError(None)
        buf += chunk
    return bytes(buf)


def _read_frame(self):
    try:
        header = _recv_exactly(self.sock, 2)
    except (ssl.SSLError, SocketClosedError):
        raise NoHeaderException()
    fin, opcode, masked_len = header[0] & 0x80, header[0] & 0x0F, header[1]
    length = masked_len & 0x7F
    if length == 126:
        length = struct.unpack('>H', _recv_exactly(self.sock, 2))[0]
    elif length == 127:
        length = struct.unpack('>Q', _recv_exactly(self.sock, 8))[0]
    if masked_len & 0x80:
        key = _recv_exactly(self.sock, 4)
        data = bytes(b ^ key[i % 4] for i, b in enumerate(_recv_exactly(self.sock, length)))
    else:
        data = _recv_exactly(self.sock, length)
    return bool(fin), opcode, data


def _recv_frame_full(self):
    fin, opcode, payload = _read_frame(self)
    if opcode == 0x8:
        raise SocketClosedError(None)
    while not fin:
        fin, op, more = _read_frame(self)
        if op == 0x8:
            raise SocketClosedError(None)
        payload += more
    return self.prepare_data(payload)


for _name in dir(_wc):
    _cls = getattr(_wc, _name)
    if isinstance(_cls, type) and '_recv_frame' in vars(_cls):
        _cls._recv_frame = _recv_frame_full

from fastf1.livetiming.client import SignalRClient  # noqa: E402

if __name__ == '__main__':
    out = sys.argv[1] if len(sys.argv) > 1 else 'tmp/live_timing.txt'
    print(f'Recording live timing to {out}. Leave this window open; press Ctrl+C to stop.')
    # Append, never truncate: FastF1's default filemode 'w' would wipe an existing recording of the same name.
    SignalRClient(out, filemode='a', timeout=1800, no_auth=True).start()
