#!/usr/bin/env bash
# 在跳板机 45.77.19.55 上运行一次，授权 NAS 用 SSH 动态转发出海。
#
#   ssh root@45.77.19.55 'bash -s' < scripts/jumphost_authorize.sh
#   或者把本文件内容贴到跳板机的 shell 里执行
#
# 做了什么：只往 ~/.ssh/authorized_keys 追加一把公钥，并限制这把钥匙只能做端口转发。
# 没有动 sing-box，没有改 sshd_config，没有装任何软件，不影响正在连 VPN 的机器。
set -euo pipefail

NAS_KEY="ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAICSnnQNNe0aR4oRJZ8b56pc7nCtDxunVThQPXYW/UyFd haifeng.zhao@wearable-aac.com"
# restrict = 关掉 pty/agent/X11 等一切；再单独放开端口转发，供 ssh -D 使用
OPTS='restrict,port-forwarding,command="/bin/false"'

mkdir -p ~/.ssh && chmod 700 ~/.ssh
touch ~/.ssh/authorized_keys && chmod 600 ~/.ssh/authorized_keys

KEY_BODY=$(awk '{print $2}' <<<"$NAS_KEY")
if grep -qF "$KEY_BODY" ~/.ssh/authorized_keys; then
  echo "公钥已存在，未重复添加"
else
  printf '%s %s\n' "$OPTS" "$NAS_KEY" >> ~/.ssh/authorized_keys
  echo "已授权 NAS 公钥（仅端口转发）"
fi

echo "--- 当前 authorized_keys 行数: $(wc -l < ~/.ssh/authorized_keys)"
echo "--- sing-box 状态（应保持 active，本脚本不会动它）"
systemctl is-active sing-box 2>/dev/null || echo "  未用 systemd 管理或服务名不同，忽略"
echo
echo "完成。回到 NAS 验证："
echo "  ssh -o BatchMode=yes -p 22 root@45.77.19.55 true && echo OK"
