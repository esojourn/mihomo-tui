# mnode

命令行下管理 [mihomo](https://github.com/MetaCubeX/mihomo)（Clash.Meta 内核）代理节点的小工具。适合在纯命令行服务器上使用——不需要 GUI、不需要 zashboard，直接在终端选节点、测速、切换。

`mnode` 通过 mihomo 的 `external-controller` REST API 操作，功能等价于 zashboard 里点选节点的操作。

## 功能

- 一键开关代理服务（`on` / `off`）
- 列出策略组和节点，标注当前选中项
- 按编号或名称切换节点
- 全组节点测速并按延迟排序
- 查看当前出口 IP
- 从 base64 订阅重建配置：候选配置验证、失败回滚、运行中自动重启
- 在 mixed-port 与 TUN 接入模式间安全切换（`mnode mode`）

## 依赖

- [mihomo](https://github.com/MetaCubeX/mihomo) 二进制，且以 systemd 服务 `mihomo` 运行
- mihomo 配置里开启了 `external-controller`（默认 `127.0.0.1:9090`）
- `python3`、`curl`、`bash`
- `build-config.py` 需要一个 base64 编码的 Shadowsocks (SIP002 `ss://`) 订阅

## 安装

```bash
sudo install -m 755 mnode /usr/local/bin/mnode
```

`build-config.py` 放到 mihomo 配置目录（默认 `/etc/mihomo/`）即可。

## 快速上手

```bash
mnode on              # 启动 mihomo
mnode list            # 列出节点，* 是当前选中
mnode test            # 测速，按延迟排序
mnode use 2           # 切到 2 号节点
mnode use AUTO        # 交给自动测速组
mnode ip              # 查看当前出口 IP
mnode off             # 用完关掉
mnode mode            # 查看当前接入模式
mnode mode tun        # 切换到 TUN（远程 SSH 默认拒绝）
mnode mode mixed      # 切回 7890 mixed-port
```

`mixed` 模式通过 `127.0.0.1:7890` 提供 HTTP 和 SOCKS5 代理，需要应用显式使用代理端口。`tun` 模式启用系统透明代理并同时保留 7890 端口，通常不需要设置代理环境变量，但仍兼容需要显式代理的程序。远程 SSH 会话切换 TUN 可能导致断联，建议使用云控制台或第二条管理链路；确需从 SSH 操作时显式使用 `--allow-ssh-risk`。

让终端流量走代理：

```bash
export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890
```

完整命令和更新订阅说明见 [USAGE.md](USAGE.md)。

## 配置约定

`mnode` 支持以下环境变量覆盖默认值：

| 变量 | 默认 | 说明 |
|------|------|------|
| `MIHOMO_API` | `http://127.0.0.1:9090` | external-controller 地址 |
| `MIHOMO_SECRET` | 空 | API 密钥（如已设置） |
| `MIHOMO_GROUP` | `PROXY` | 默认操作的策略组 |

## 文件说明

- `mnode` — 主脚本
- `build-config.py` — 把 base64 的 `ss://` 订阅转换成 mihomo `config.yaml`
- `USAGE.md` — 完整中文操作文档

## 安全说明

- 默认所有端口只监听 `127.0.0.1`，不对外暴露。
- **订阅链接、`sub.b64`、生成的 `config.yaml` 都含有凭据，请勿提交到仓库**（见 `.gitignore`）。
- 若开放 `allow-lan` 或改动 API 监听地址，务必先给 API 设置 `secret`。

## License

MIT
