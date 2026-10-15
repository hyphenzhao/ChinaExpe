"""sing-box 分享链接解析与配置生成。全部用虚构凭据。"""
import base64
import json

import pytest

from app.services import singbox_service as S

UUID = "11111111-2222-3333-4444-555555555555"


def test_vless_reality_vision():
    ob = S.parse(f"vless://{UUID}@203.0.113.5:443?encryption=none&flow=xtls-rprx-vision&security=reality"
                 "&sni=www.example.com&fp=chrome&pbk=PUBKEY&sid=ab12&type=tcp#node")
    assert ob["type"] == "vless" and ob["server"] == "203.0.113.5" and ob["server_port"] == 443
    assert ob["uuid"] == UUID and ob["flow"] == "xtls-rprx-vision"
    assert ob["tls"]["server_name"] == "www.example.com"
    assert ob["tls"]["reality"] == {"enabled": True, "public_key": "PUBKEY", "short_id": "ab12"}
    assert ob["tls"]["utls"]["fingerprint"] == "chrome" and "transport" not in ob


def test_vless_ws_tls():
    ob = S.parse(f"vless://{UUID}@a.example.com:8443?security=tls&type=ws&path=%2Fray&host=cdn.example.com")
    assert ob["transport"] == {"type": "ws", "path": "/ray", "headers": {"Host": "cdn.example.com"}}
    assert ob["tls"]["enabled"] and "reality" not in ob["tls"]


def test_hysteria2_and_trojan_and_tuic():
    h = S.parse("hysteria2://secret@203.0.113.5:8443?sni=h.example.com&insecure=1&obfs=salamander&obfs-password=x")
    assert h["type"] == "hysteria2" and h["password"] == "secret" and h["tls"]["insecure"]
    assert h["obfs"] == {"type": "salamander", "password": "x"}
    t = S.parse("trojan://pw@203.0.113.5:443?sni=t.example.com")
    assert t["type"] == "trojan" and t["tls"]["server_name"] == "t.example.com"
    u = S.parse(f"tuic://{UUID}:pw@203.0.113.5:443?congestion_control=bbr&alpn=h3")
    assert u["type"] == "tuic" and u["password"] == "pw" and u["tls"]["alpn"] == ["h3"]


def test_ss_both_forms():
    userinfo = base64.urlsafe_b64encode(b"aes-128-gcm:pw").decode().rstrip("=")
    a = S.parse(f"ss://{userinfo}@203.0.113.5:8388#n")
    whole = base64.b64encode(b"aes-128-gcm:pw@203.0.113.5:8388").decode()
    b = S.parse(f"ss://{whole}#n")
    for ob in (a, b):
        assert ob == {"type": "shadowsocks", "server": "203.0.113.5", "server_port": 8388,
                      "method": "aes-128-gcm", "password": "pw"}


def test_vmess():
    j = {"add": "203.0.113.5", "port": "443", "id": UUID, "aid": "0", "net": "ws", "path": "/v", "tls": "tls", "sni": "v.example.com"}
    ob = S.parse("vmess://" + base64.b64encode(json.dumps(j).encode()).decode())
    assert ob["type"] == "vmess" and ob["server_port"] == 443 and ob["transport"]["type"] == "ws"
    assert ob["tls"]["server_name"] == "v.example.com"


def test_json_full_config_takes_first_proxy_outbound():
    full = {"outbounds": [{"type": "direct", "tag": "direct"},
                          {"type": "vless", "tag": "proxy", "server": "203.0.113.5", "server_port": 443, "uuid": UUID}]}
    ob = S.parse(json.dumps(full))
    assert ob["type"] == "vless" and "tag" not in ob


def test_bad_input():
    with pytest.raises(ValueError):
        S.parse("http://example.com")
    with pytest.raises(ValueError):
        S.parse(json.dumps({"outbounds": [{"type": "direct"}]}))


def test_build_config_and_check():
    conf = S.build_config(S.parse(f"vless://{UUID}@203.0.113.5:443?security=reality&sni=www.example.com&pbk=cHVia2V5cHVia2V5cHVia2V5cHVia2V5cHVia2V5cHU&sid=ab12"), port=11080)
    assert conf["inbounds"][0]["listen_port"] == 11080 and conf["route"]["final"] == "jump"
    if not S.binary():
        pytest.skip("本机没有 sing-box")
    ok, msg = S.check(conf)
    assert ok, msg


def test_save_writes_private_file(tmp_path, monkeypatch):
    if not S.binary():
        pytest.skip("本机没有 sing-box")
    monkeypatch.setattr(S, "CONF_DIR", tmp_path)
    monkeypatch.setattr(S, "CONF_PATH", tmp_path / "x.json")
    info = S.save("trojan://pw@203.0.113.5:443?sni=t.example.com", port=11081)
    assert info["type"] == "trojan" and info["server"] == "203.0.113.5"
    assert "pw" not in json.dumps(info)                           # 摘要不含凭据
    assert (tmp_path / "x.json").stat().st_mode & 0o077 == 0
