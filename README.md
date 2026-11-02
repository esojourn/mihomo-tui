# mnode

命令行下管理 [mihomo](https://github.com/MetaCubeX/mihomo)（Clash.Meta 内核）代理节点的小工具。适合在纯命令行服务器上使用——不需要 GUI、不需要 zashboard，直接在终端选节点、测速、切换。

`mnode` 通过 mihomo 的 `external-controller` REST API 操作，功能等价于 zashboard 里点选节点的操作。

## 功能

- 中文数字菜单（`mnode tui` / `mnode menu`），支持分页、筛选和切换策略组
- 固定版本、多来源摘要校验安装，支持离线部署和升级回滚
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

获取同一版本的完整项目文件和本地订阅后：

```bash
sudo bash install.sh --subscription ./sub.b64
mnode tui
```

首次安装默认 mixed 模式，**不启动服务、不启用开机启动**。支持 Debian/Ubuntu、RHEL 系的 systemd 环境，amd64 compatible 和 arm64。需要 Python 3.8+、curl、util-linux（flock、unshare）及 root 网络命名空间权限。

在线来源、固定提交下载、依赖准备、`scp` 上传目录、离线安装和升级恢复见 [INSTALL.md](INSTALL.md)。常用离线命令：

```bash
# 联网机器准备目标架构资源
bash install.sh --download-only --arch amd64 --assets-dir ./assets
# 将完整目录与订阅上传后，在目标机器执行
sudo bash install.sh --offline --assets-dir ./assets --subscription ./sub.b64
# 保留配置与订阅，升级到随项目清单固定的版本
sudo bash install.sh --upgrade --offline --assets-dir ./assets
```

## 快速上手

```bash
mnode tui             # 中文数字菜单（也可 mnode menu）
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
| `MIHOMO_CONFIG_DIR` | `/etc/mihomo` | CLI 配置目录 |
| `MIHOMO_BIN` | `/usr/local/bin/mihomo` | CLI 验证配置的内核 |

## 文件说明

- `install.sh` / `install.py` — 安装、资源准备与升级
- `assets.json` / `project-sha256.json` — 固定资源与 SHA-256 清单
- `mnode-tui.py` — Python 标准库数字菜单
- `INSTALL.md` — 在线与离线安装文档
- `test-mnode.py` — 隔离回归测试
- `mnode` — 主脚本
- `build-config.py` — 把 base64 的 `ss://` 订阅转换成 mihomo `config.yaml`
- `USAGE.md` — 完整中文操作文档

## 安全说明

- 默认所有端口只监听 `127.0.0.1`，不对外暴露。
- **订阅链接、`sub.b64`、生成的 `config.yaml` 都含有凭据，请勿提交到仓库**（见 `.gitignore`）。
- 若开放 `allow-lan` 或改动 API 监听地址，务必先给 API 设置 `secret`。

## License

MIT
