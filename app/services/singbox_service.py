"""sing-box 客户端配置：把分享链接或 outbound JSON 变成本机 SOCKS5 → 跳板机 sing-box 的配置。

NAS 到跳板机的 SSH 直连丢包严重（大陆到海外的 SSH 常被限速），而跳板机上本来就跑着 sing-box
服务端，所以改由本机 sing-box 客户端连它，对外仍是 127.0.0.1:1080 的 SOCKS5，应用其余部分不变。
跳板机上不做任何改动。

配置文件含凭据，放在仓库之外（~/.config/sing-box/xuanxue.json，权限 600），页面只看得到摘要。
"""
from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

CONF_DIR = Path(os.environ.get("XUANXUE_SINGBOX_DIR", Path.home() / ".config" / "sing-box"))
CONF_PATH = CONF_DIR / "xuanxue.json"
LOG_PATH = CONF_DIR / "xuanxue.log"
PROXY_TYPES = {"vless", "vmess", "trojan", "hysteria2", "hysteria", "tuic", "shadowsocks", "anytls",
               "shadowtls", "wireguard", "ssh", "socks", "http"}


def binary() -> str | None:
    for p in (os.environ.get("XUANXUE_SINGBOX_BIN"), str(Path.home() / ".local" / "bin" / "sing-box"),
              shutil.which("sing-box")):
        if p and os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return None


# ------------------------------------------------------------------ parsing
def _b64(s: str) -> str:
    s = s.strip().replace("-", "+").replace("_", "/")
    return base64.b64decode(s + "=" * (-len(s) % 4)).decode("utf-8")


def _q(query: str) -> dict[str, str]:
    return {k: v[0] for k, v in parse_qs(query, keep_blank_values=True).items()}


def _truthy(v: str | None) -> bool:
    return str(v or "").lower() in ("1", "true", "yes")


def _tls(q: dict, host: str, default_on: bool = False) -> dict | None:
    sec = q.get("security", "tls" if default_on else "none")
    if sec in ("", "none") and not default_on:
        return None
    tls: dict = {"enabled": True, "server_name": q.get("sni") or q.get("peer") or host}
    if _truthy(q.get("allowInsecure") or q.get("insecure")):
        tls["insecure"] = True
    if q.get("alpn"):
        tls["alpn"] = [a for a in unquote(q["alpn"]).split(",") if a]
    fp = q.get("fp")
    if fp or sec == "reality":
        tls["utls"] = {"enabled": True, "fingerprint": fp or "chrome"}
    if sec == "reality":
        tls["reality"] = {"enabled": True, "public_key": q.get("pbk", ""), "short_id": q.get("sid", "")}
    return tls


def _transport(q: dict) -> dict | None:
    t = q.get("type") or q.get("net") or "tcp"
    host, path = q.get("host", ""), unquote(q.get("path", "")) or "/"
    if t == "ws":
        tr = {"type": "ws", "path": path}
        if host:
            tr["headers"] = {"Host": host}
        return tr
    if t == "grpc":
        return {"type": "grpc", "service_name": q.get("serviceName") or q.get("path", "")}
    if t == "httpupgrade":
        return {"type": "httpupgrade", "path": path, **({"host": host} if host else {})}
    if t in ("http", "h2"):
        return {"type": "http", "path": path, **({"host": [host]} if host else {})}
    return None


def parse_link(link: str) -> dict:
    """分享链接 → sing-box outbound。支持 vless / vmess / trojan / hysteria2 / tuic / ss。"""
    link = link.strip()
    scheme = link.split("://", 1)[0].lower()
    if scheme == "vmess":
        j = json.loads(_b64(link[8:].split("#")[0]))
        q = {"security": "tls" if j.get("tls") in ("tls", True) else "none", "sni": j.get("sni", ""),
             "type": j.get("net", "tcp"), "host": j.get("host", ""), "path": j.get("path", ""),
             "alpn": j.get("alpn", ""), "fp": j.get("fp", "")}
        ob = {"type": "vmess", "server": j["add"], "server_port": int(j["port"]), "uuid": j["id"],
              "security": j.get("scy") or "auto", "alter_id": int(j.get("aid") or 0)}
        if (t := _tls(q, j["add"])):
            ob["tls"] = t
        if (tr := _transport(q)):
            ob["transport"] = tr
        return ob

    if scheme == "ss" and "@" not in link.split("#")[0]:
        body = link[5:].split("#")[0]
        link = "ss://" + _b64(body.split("?")[0])
    u = urlparse(link)
    q = _q(u.query)
    host, port = u.hostname, u.port
    if not host or not port:
        raise ValueError("链接里缺少服务器地址或端口")
    user = unquote(u.username or "")
    pw = unquote(u.password or "")

    if scheme == "vless":
        ob = {"type": "vless", "server": host, "server_port": port, "uuid": user}
        if q.get("flow"):
            ob["flow"] = q["flow"]
        if (t := _tls(q, host)):
            ob["tls"] = t
        if (tr := _transport(q)):
            ob["transport"] = tr
        return ob
    if scheme == "trojan":
        ob = {"type": "trojan", "server": host, "server_port": port, "password": user,
              "tls": _tls(q, host, default_on=True)}
        if (tr := _transport(q)):
            ob["transport"] = tr
        return ob
    if scheme in ("hysteria2", "hy2"):
        ob = {"type": "hysteria2", "server": host, "server_port": port,
              "password": f"{user}:{pw}" if pw else user,
              "tls": _tls({**q, "security": "tls"}, host, default_on=True)}
        if q.get("obfs"):
            ob["obfs"] = {"type": q["obfs"], "password": q.get("obfs-password", "")}
        return ob
    if scheme == "tuic":
        ob = {"type": "tuic", "server": host, "server_port": port, "uuid": user, "password": pw,
              "congestion_control": q.get("congestion_control", "bbr"),
              "tls": _tls({**q, "security": "tls"}, host, default_on=True)}
        return ob
    if scheme == "ss":
        if not pw:                              # ss://base64(method:password)@host:port
            user, pw = _b64(user).split(":", 1)
        return {"type": "shadowsocks", "server": host, "server_port": port, "method": user, "password": pw}
    raise ValueError(f"不支持的链接类型: {scheme}://")


def parse(text: str) -> dict:
    """接受分享链接、单个 outbound JSON、或完整的 sing-box 配置（取第一个代理类 outbound）。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("内容为空")
    if text.startswith("{"):
        j = json.loads(text)
        if j.get("type") in PROXY_TYPES:
            ob = j
        else:
            obs = [o for o in j.get("outbounds", []) if o.get("type") in PROXY_TYPES]
            if not obs:
                raise ValueError("JSON 里没有找到代理类 outbound（vless/trojan/hysteria2 等）")
            ob = obs[0]
        ob = {k: v for k, v in ob.items() if k not in ("tag", "detour", "domain_resolver")}
        return ob
    return parse_link(text.splitlines()[0])


# ------------------------------------------------------------------ config file
def build_config(outbound: dict, listen: str = "127.0.0.1", port: int = 1080) -> dict:
    return {
        "log": {"level": "warn", "timestamp": True},
        "dns": {"servers": [{"type": "local", "tag": "local"}]},
        "inbounds": [{"type": "socks", "tag": "socks-in", "listen": listen, "listen_port": port}],
        "outbounds": [{**outbound, "tag": "jump"}, {"type": "direct", "tag": "direct"}],
        "route": {"final": "jump", "default_domain_resolver": "local"},
    }


def check(conf: dict) -> tuple[bool, str]:
    b = binary()
    if not b:
        return False, "本机没有 sing-box（应在 ~/.local/bin/sing-box）"
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(conf, f)
        tmp = f.name
    try:
        r = subprocess.run([b, "check", "-c", tmp], capture_output=True, text=True, timeout=20)
        return r.returncode == 0, (r.stderr or r.stdout).strip()[:300]
    finally:
        os.unlink(tmp)


def save(text: str, listen: str = "127.0.0.1", port: int = 1080) -> dict:
    ob = parse(text)
    conf = build_config(ob, listen, port)
    ok, msg = check(conf)
    if not ok:
        raise ValueError(f"sing-box 校验未通过: {msg}")
    CONF_DIR.mkdir(parents=True, exist_ok=True)
    fd = os.open(CONF_PATH, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        json.dump(conf, f, ensure_ascii=False, indent=2)
    os.chmod(CONF_PATH, 0o600)
    return summary()


def rebind(listen: str, port: int) -> None:
    """SOCKS 地址改了时同步到已存的配置里。"""
    if not CONF_PATH.exists():
        return
    conf = json.loads(CONF_PATH.read_text())
    inb = conf.get("inbounds", [{}])[0]
    if inb.get("listen") != listen or inb.get("listen_port") != port:
        inb["listen"], inb["listen_port"] = listen, port
        CONF_PATH.write_text(json.dumps(conf, ensure_ascii=False, indent=2))
        os.chmod(CONF_PATH, 0o600)


def summary() -> dict:
    """只给页面看的摘要，不含 uuid / 密码 / 密钥。"""
    info = {"binary": binary(), "configured": CONF_PATH.exists(), "path": str(CONF_PATH)}
    if not info["configured"]:
        return info
    try:
        conf = json.loads(CONF_PATH.read_text())
        ob = next(o for o in conf["outbounds"] if o.get("tag") == "jump")
        tls = ob.get("tls") or {}
        info.update({"type": ob.get("type"), "server": ob.get("server"), "server_port": ob.get("server_port"),
                     "tls": bool(tls.get("enabled")), "reality": bool((tls.get("reality") or {}).get("enabled")),
                     "transport": (ob.get("transport") or {}).get("type", "tcp")})
    except Exception as e:
        info["error"] = f"配置读取失败: {e}"
    return info


def log_tail(n: int = 400) -> str:
    try:
        return LOG_PATH.read_text(errors="ignore")[-n:].strip()
    except OSError:
        return ""
