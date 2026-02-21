#!/usr/bin/env python3
"""
ZeroMQ REP server for the [python-xray-controller-application] main controller.
Binds to tcp://127.0.0.1:5555 and implements the camera API:
  ping, set_exposure_ms, set_gain, set_stack_n, take_snapshot.
Response format: {"ok": true, ...} or {"ok": false, "error": "..."}.
take_snapshot returns {"ok": true, "path": "<file path>"}.
"""

import sys
import time
import threading
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, Optional

# Ensure parent dir is on path so "from lib.hamamatsu_teensy import HamamatsuTeensy" works when run as script
_here = Path(__file__).resolve().parent
if _here.parent not in [Path(p).resolve() for p in sys.path]:
    sys.path.insert(0, str(_here.parent))

import zmq

try:
    from lib.hamamatsu_teensy import HamamatsuTeensy
    FRAME_HEIGHT = HamamatsuTeensy.FRAME_HEIGHT
    FRAME_WIDTH = HamamatsuTeensy.FRAME_WIDTH
except ImportError:
    HamamatsuTeensy = None  # type: ignore
    FRAME_WIDTH = 2400
    FRAME_HEIGHT = 2400

# Default snapshot output directory (main controller expects a path)
DEFAULT_SNAPSHOT_DIR = Path(tempfile.gettempdir()) / "hamamatsu_snapshots"


def _trigger_and_read(teensy) -> Optional[Any]:
    """One shot: trigger, wait for DONE, return float32 (H,W) or None on stop."""
    if HamamatsuTeensy is None:
        raise RuntimeError("HamamatsuTeensy not available")
    teensy.start_trigger()
    for _ in range(200):  # 20 s timeout
        state = teensy.get_state()
        if state["state"] == 3:  # DONE
            break
        time.sleep(0.1)
    else:
        raise TimeoutError("Frame acquisition timed out")
    raw = teensy.get_frame()
    import numpy as np
    pixels = HamamatsuTeensy.unpack_12bit(raw)
    return pixels.reshape((FRAME_HEIGHT, FRAME_WIDTH)).astype(np.float32)


def _save_tiff(path: Path, frame, dtype_uint16: bool = True) -> None:
    """Save 2D array as TIFF (16-bit if dtype_uint16 else 8-bit)."""
    import numpy as np
    from PIL import Image
    path.parent.mkdir(parents=True, exist_ok=True)
    if dtype_uint16:
        arr = np.clip(frame, 0, 65535).astype(np.uint16)
        arr = arr.astype(arr.dtype.newbyteorder("<"))  # little-endian
        img = Image.new("I;16", (arr.shape[1], arr.shape[0]))
        img.frombytes(arr.tobytes())
    else:
        arr = np.clip(frame, 0, 255).astype(np.uint8)
        img = Image.fromarray(arr, mode="L")
    img.save(str(path), compression="tiff_lzw")


class CameraZMQServer:
    """
    REP socket server that implements the main controller camera API.
    get_teensy: callable() -> HamamatsuTeensy | None. Called for take_snapshot.
    snapshot_dir: directory to write take_snapshot TIFFs.
    """

    def __init__(
        self,
        addr: str = "tcp://127.0.0.1:5555",
        get_teensy: Optional[Callable[[], Any]] = None,
        snapshot_dir: Optional[Path] = None,
    ):
        self.addr = addr
        self.get_teensy = get_teensy or (lambda: None)
        self.snapshot_dir = Path(snapshot_dir) if snapshot_dir else DEFAULT_SNAPSHOT_DIR
        self._exposure_ms = 100
        self._gain = 0
        self._stack_n = 1
        self._ctx = None
        self._sock = None
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()

    def start(self) -> bool:
        """Start the server. Returns True if bound successfully, False if port in use."""
        if self._thread is not None and self._thread.is_alive():
            return True
        self._stop.clear()
        self._ctx = zmq.Context.instance()
        self._sock = self._ctx.socket(zmq.REP)
        try:
            self._sock.bind(self.addr)
        except zmq.ZMQError as e:
            in_use = (getattr(zmq, "EADDRINUSE", None) is not None and e.errno == zmq.EADDRINUSE) or "Address in use" in str(e) or "Address already in use" in str(e)
            if in_use:
                import sys
                print(f"ZMQ: port 5555 in use, server not started. {e}", file=sys.stderr)
            else:
                raise
            self._sock.close()
            self._sock = None
            return False
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._stop.set()
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
            self._sock = None
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self._thread = None

    def _serve(self) -> None:
        poller = zmq.Poller()
        poller.register(self._sock, zmq.POLLIN)
        while not self._stop.is_set():
            try:
                socks = dict(poller.poll(200))
            except Exception:
                continue
            if self._sock not in socks:
                continue
            try:
                msg = self._sock.recv_json()
            except Exception as e:
                self._reply({"ok": False, "error": str(e)})
                continue
            payload = self._handle(msg)
            self._reply(payload)

    def _reply(self, payload: Dict[str, Any]) -> None:
        try:
            self._sock.send_json(payload)
        except Exception:
            pass

    def _handle(self, msg: Dict[str, Any]) -> Dict[str, Any]:
        cmd = (msg or {}).get("cmd")
        args = (msg or {}).get("args") or {}
        value = args.get("value") if isinstance(args, dict) else None

        if cmd == "ping":
            return {"ok": True}

        if cmd == "set_exposure_ms":
            try:
                self._exposure_ms = int(value) if value is not None else 100
                return {"ok": True}
            except (TypeError, ValueError):
                return {"ok": False, "error": "Invalid exposure_ms"}

        if cmd == "set_gain":
            try:
                self._gain = int(value) if value is not None else 0
                return {"ok": True}
            except (TypeError, ValueError):
                return {"ok": False, "error": "Invalid gain"}

        if cmd == "set_stack_n":
            try:
                n = int(value) if value is not None else 1
                self._stack_n = max(1, min(999, n))
                return {"ok": True}
            except (TypeError, ValueError):
                return {"ok": False, "error": "Invalid stack_n"}

        if cmd == "take_snapshot":
            return self._take_snapshot()

        return {"ok": False, "error": f"Unknown command: {cmd}"}

    def _take_snapshot(self) -> Dict[str, Any]:
        teensy = self.get_teensy() if callable(self.get_teensy) else None
        if teensy is None:
            return {"ok": False, "error": "Camera not connected"}

        try:
            import numpy as np
            n = max(1, self._stack_n)
            frames = []
            for _ in range(n):
                frame = _trigger_and_read(teensy)
                if frame is None:
                    return {"ok": False, "error": "Capture stopped"}
                frames.append(frame)
            stacked = np.mean(frames, axis=0).astype(np.float32)

            # Optional: apply Faxitron exposure from exposure_ms before first shot
            # (e.g. teensy.set_faxitron_exposure_time(self._exposure_ms / 1000.0))
            # Skipped here so GUI/Faxitron panel remains source of truth.

            self.snapshot_dir.mkdir(parents=True, exist_ok=True)
            name = f"hamamatsu_{time.strftime('%Y%m%d_%H%M%S')}.tif"
            path = self.snapshot_dir / name
            _save_tiff(path, stacked, dtype_uint16=True)
            return {"ok": True, "path": str(path.resolve())}
        except Exception as e:
            return {"ok": False, "error": str(e)}


def main() -> None:
    """Headless entrypoint: start ZMQ server; Teensy is connected on first take_snapshot."""
    if HamamatsuTeensy is None:
        print("ERROR: cannot import HamamatsuTeensy (run from repo root or install app)", file=sys.stderr)
        sys.exit(1)
    server = CameraZMQServer(addr="tcp://127.0.0.1:5555")
    teensy_ref = [None]  # mutable so get_teensy can set it

    def get_teensy():
        if teensy_ref[0] is None:
            try:
                t = HamamatsuTeensy()
                t.ping()
                teensy_ref[0] = t
            except Exception:
                return None
        return teensy_ref[0]

    server.get_teensy = get_teensy
    server.start()
    print("Camera ZMQ server listening on", server.addr, file=sys.stderr)
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        server.stop()


if __name__ == "__main__":
    main()
