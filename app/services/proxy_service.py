"""跳板 (jump host) tunnel for the overseas APIs.

api.openai.com is unreachable from the NAS and api.anthropic.com answers 403,
so those two providers can be routed through 45.77.19.55.  The tunnel is a
plain SSH dynamic forward started as the normal app user:

    ssh -N -D 127.0.0.1:1080 <user>@<host>

Nothing is installed or reconfigured on the jump host, so the sing-box service
running there is untouched — this only opens an extra SSH session.  The user
turns it on and off in the settings page; DeepSeek and Ollama keep going direct.

proxy_mode = "singbox" runs a local sing-box client instead (see singbox_service):
plain SSH from the mainland to the VPS loses most of its packets, while the
sing-box server on the jump host is built for exactly that path.  Either way the
app only ever sees the same local SOCKS5 port.
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
from . import singbox_service

# marker so we only ever kill the tunnel we started
MARKER = "xuanxue-jumphost"
_proc: subprocess.Popen | None = None
_proc_mode: str | None = None


def _mode(cfg: ApiConfig) -> str:
    return "singbox" if getattr(cfg, "proxy_mode", "ssh") == "singbox" else "ssh"


def _via(cfg: ApiConfig) -> str:
    if _mode(cfg) == "singbox":
        s = singbox_service.summary()
        return f"sing-box {s.get('type', '未配置')} → {s.get('server', '?')}:{s.get('server_port', '?')}"
    return f"ssh {cfg.proxy_ssh_user}@{cfg.proxy_ssh_host}:{cfg.proxy_ssh_port}"


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
        "managed_mode": _proc_mode if running else None,
        "pid": _proc.pid if running else None,
        "mode": _mode(cfg),
        "via": _via(cfg),
        "ssh": f"{cfg.proxy_ssh_user}@{cfg.proxy_ssh_host}:{cfg.proxy_ssh_port}",
        "ssh_available": bool(shutil.which("ssh")),
        "singbox": singbox_service.summary(),
    }


def snapshot(cfg: ApiConfig, timeout: float = 0.3) -> dict:
    """Cheap read-only view for the chat picker; never starts anything."""
    host, port = _port_of(cfg.proxy_url)
    return {"enabled": cfg.proxy_enabled, "listening": port_open(host, port, timeout),
            "providers": cfg.proxy_providers, "proxy_url": cfg.proxy_url,
            "mode": _mode(cfg), "ssh": f"{cfg.proxy_ssh_user}@{cfg.proxy_ssh_host}"}


def warning_for(cfg: ApiConfig, provider: str, timeout: float = 0.3) -> str:
    """中文提示：这个提供商要走跳板，但跳板没准备好。空字符串表示没问题。"""
    if provider not in (cfg.proxy_providers or []):
        return ""
    if not cfg.proxy_enabled:
        return "OpenAI/Anthropic 在大陆通常需要跳板，当前跳板未启用（设置 → 海外 API 跳板）"
    host, port = _port_of(cfg.proxy_url)
    if not port_open(host, port, timeout):
        return "已启用跳板但隧道未监听，可能连不上（设置 → 海外 API 跳板 → 启动隧道）"
    return ""


def _start_singbox(cfg: ApiConfig, host: str, port: int, wait: float) -> dict:
    global _proc, _proc_mode
    b = singbox_service.binary()
    if not b:
        return {"success": False, "message": "本机没有 sing-box（应在 ~/.local/bin/sing-box）", **status(cfg)}
    if not singbox_service.CONF_PATH.exists():
        return {"success": False, "message": "还没有 sing-box 客户端配置，请先在设置里粘贴分享链接并保存", **status(cfg)}
    singbox_service.rebind(host, port)
    try:
        log = open(singbox_service.LOG_PATH, "w")          # 输出进文件，不用管道，免得写满后卡住
        _proc = subprocess.Popen([b, "run", "-c", str(singbox_service.CONF_PATH)],
                                 stdout=log, stderr=log, start_new_session=True)
        _proc_mode = "singbox"
    except Exception as e:
        return {"success": False, "message": f"启动失败: {e}", **status(cfg)}
    deadline = time.time() + wait
    while time.time() < deadline:
        if port_open(host, port):
            return {"success": True, "message": f"sing-box 已启动，SOCKS5 监听 {host}:{port}", **status(cfg)}
        if _proc.poll() is not None:
            _proc = None
            return {"success": False, "message": f"sing-box 退出: {singbox_service.log_tail(200)}", **status(cfg)}
        time.sleep(0.3)
    return {"success": False, "message": "启动超时，端口未监听", **status(cfg)}


def start(cfg: ApiConfig, wait: float = 20.0) -> dict:
    """Start the tunnel (SSH dynamic forward or sing-box) if the port is not already serving."""
    global _proc, _proc_mode
    host, port = _port_of(cfg.proxy_url)
    if port_open(host, port):
        return {"success": True, "message": f"跳板已在 {host}:{port} 监听", **status(cfg)}
    if _mode(cfg) == "singbox":
        return _start_singbox(cfg, host, port, wait)
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
        _proc_mode = "ssh"
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
    global _proc, _proc_mode
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
    _proc_mode = None
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
