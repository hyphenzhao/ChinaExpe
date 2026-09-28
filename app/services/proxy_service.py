"""跳板 (jump host) tunnel for the overseas APIs.

api.openai.com is unreachable from the NAS and api.anthropic.com answers 403,
so those two providers can be routed through 45.77.19.55.  The tunnel is a
plain SSH dynamic forward started as the normal app user:

    ssh -N -D 127.0.0.1:1080 <user>@<host>

Nothing is installed or reconfigured on the jump host, so the sing-box service
running there is untouched — this only opens an extra SSH session.  The user
turns it on and off in the settings page; DeepSeek and Ollama keep going direct.
"""
from __future__ import annotations

import os
import shutil
import signal
import socket
import subprocess
import time
from urllib.parse import urlparse

from ..models.config import ApiConfig

# marker so we only ever kill the tunnel we started
MARKER = "xuanxue-jumphost"
_proc: subprocess.Popen | None = None


def _port_of(proxy_url: str) -> tuple[str, int]:
    u = urlparse(proxy_url or "")
    return (u.hostname or "127.0.0.1", u.port or 1080)


def port_open(host: str, port: int, timeout: float = 1.0) -> bool:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def status(cfg: ApiConfig) -> dict:
    host, port = _port_of(cfg.proxy_url)
    running = _proc is not None and _proc.poll() is None
    return {
        "enabled": cfg.proxy_enabled,
        "proxy_url": cfg.proxy_url,
        "providers": cfg.proxy_providers,
        "listening": port_open(host, port),
        "managed_by_app": running,
        "pid": _proc.pid if running else None,
        "ssh": f"{cfg.proxy_ssh_user}@{cfg.proxy_ssh_host}:{cfg.proxy_ssh_port}",
        "ssh_available": bool(shutil.which("ssh")),
    }


def start(cfg: ApiConfig, wait: float = 6.0) -> dict:
    """Start the SSH dynamic forward if the port is not already serving."""
    global _proc
    host, port = _port_of(cfg.proxy_url)
    if port_open(host, port):
        return {"success": True, "message": f"跳板已在 {host}:{port} 监听", **status(cfg)}
    if not shutil.which("ssh"):
        return {"success": False, "message": "本机没有 ssh 命令", **status(cfg)}
    cmd = [
        "ssh", "-N", "-D", f"{host}:{port}",
        "-o", "BatchMode=yes",                  # never prompt: fail fast if the key is not authorised
        "-o", "ExitOnForwardFailure=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ServerAliveInterval=30",
        "-o", "ServerAliveCountMax=3",
        "-o", f"SetEnv={MARKER}=1",
        "-p", str(cfg.proxy_ssh_port),
        f"{cfg.proxy_ssh_user}@{cfg.proxy_ssh_host}",
    ]
    try:
        _proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 start_new_session=True)
    except Exception as e:
        return {"success": False, "message": f"启动失败: {e}", **status(cfg)}
    deadline = time.time() + wait
    while time.time() < deadline:
        if port_open(host, port):
            return {"success": True, "message": f"跳板已启动，SOCKS5 监听 {host}:{port}", **status(cfg)}
        if _proc.poll() is not None:
            err = (_proc.stderr.read() or b"").decode("utf-8", "ignore").strip() if _proc.stderr else ""
            _proc = None
            hint = "（多半是跳板机还没授权本机公钥，见 README 的跳板一节）" if "denied" in err.lower() else ""
            return {"success": False, "message": f"ssh 退出: {err[:200]}{hint}", **status(cfg)}
        time.sleep(0.3)
    return {"success": False, "message": "启动超时，端口未监听", **status(cfg)}


def stop(cfg: ApiConfig) -> dict:
    global _proc
    if _proc is not None and _proc.poll() is None:
        try:
            os.killpg(os.getpgid(_proc.pid), signal.SIGTERM)
        except Exception:
            _proc.terminate()
        try:
            _proc.wait(timeout=5)
        except Exception:
            pass
    _proc = None
    host, port = _port_of(cfg.proxy_url)
    still = port_open(host, port)
    return {"success": not still,
            "message": "跳板已停止" if not still else f"{host}:{port} 仍在监听（可能是你手工起的隧道，本程序不会去动它）",
            **status(cfg)}


def ensure(cfg: ApiConfig) -> dict:
    """Called at startup and after a settings change."""
    if cfg.proxy_enabled and cfg.proxy_autostart:
        return start(cfg)
    return status(cfg)
