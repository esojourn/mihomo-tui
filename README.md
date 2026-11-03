# Mihomo TUI

无需 GUI，通过中文终端菜单管理 [mihomo](https://github.com/MetaCubeX/mihomo)（Clash.Meta 内核）代理节点的小工具。适合在纯命令行服务器上使用——不需要 GUI、不需要 zashboard，直接在终端选节点、测速、切换。

`mihomo-tui` 通过 mihomo 的 `external-controller` REST API 操作，功能等价于 zashboard 里点选节点的操作。

## 交互安装与离线包

上传完整项目目录后运行 `sudo bash install.sh`，按中文向导选择本地资源或在线来源，再输入订阅链接、粘贴内容（单独一行 `.` 结束）或提供文件。支持 SS 明文/Base64 和含内嵌 `proxies` 的 Clash YAML；只导入节点，不采用服务商的规则、DNS、TUN 和监听配置，不支持仅含远程 provider 的订阅。

首次安装确认后可启动本地 mixed 并查询出口；不修改系统路由、DNS、防火墙或全局代理变量。开机自启单独选择，默认关闭。Python、curl 等缺失时，向导可经确认使用现有系统源安装；离线包不包含发行版系统依赖。

制作可上传的软件包（输出路径需自行指定）：

```bash
bash install.sh --bundle light --output /tmp/mihomo-tui-light.tar.gz
bash install.sh --bundle offline --arch amd64 --output /tmp/mihomo-tui-amd64.tar.gz
# arm64 使用 --arch arm64
```

打包只包含明确列出的项目和资源文件，不包含本地订阅；旁边生成 `.sha256` 文件。离线包仍需已有基础系统依赖。带参数的原安装方式保持兼容。


项目原名 **mnode**。新命令 `mihomo-tui` 无参数直接打开菜单；`mnode` 命令继续兼容，原配置目录、环境变量和服务名保持不变。

## 功能

- 中文数字菜单（`mihomo-tui tui` / `mihomo-tui menu`），支持分页、筛选和切换策略组
- 固定版本、多来源摘要校验安装，支持离线部署和升级回滚
- 一键开关代理服务（`on` / `off`）
- 列出策略组和节点，标注当前选中项
- 按编号或名称切换节点
- 全组节点测速并按延迟排序
- 查看当前出口 IP
- 从 SS 明文/Base64 或 Clash YAML 订阅重建配置：候选配置验证、失败回滚、运行中自动重启
- 在 mixed-port 与 TUN 接入模式间安全切换（`mihomo-tui mode`）

## 依赖

- [mihomo](https://github.com/MetaCubeX/mihomo) 二进制，且以 systemd 服务 `mihomo` 运行
- mihomo 配置里开启了 `external-controller`（默认 `127.0.0.1:9090`）
- `python3`、`curl`、`bash`
- 订阅支持 Shadowsocks (SIP002 `ss://`) 明文/Base64，以及包含内嵌节点的 Clash YAML；YAML 解析组件已随项目附带

## 安装

获取同一版本完整项目并进入目录后：

```bash
sudo bash install.sh
```

首次安装默认 mixed 模式，向导分别询问启动与开机自启，默认均不启用。带 `--subscription` 参数安装保持停止。支持 Debian/Ubuntu、RHEL 系的 systemd 环境，amd64 compatible 和 arm64。需要 Python 3.8+、curl、util-linux（flock、unshare）及 root 网络命名空间权限。

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
mihomo-tui tui             # 中文数字菜单（也可 mihomo-tui menu）
mihomo-tui on              # 启动 mihomo
mihomo-tui list            # 列出节点，* 是当前选中
mihomo-tui test            # 测速，按延迟排序
mihomo-tui use 2           # 切到 2 号节点
mihomo-tui use AUTO        # 交给自动测速组
mihomo-tui ip              # 查看当前出口 IP
mihomo-tui off             # 用完关掉
mihomo-tui mode            # 查看当前接入模式
mihomo-tui mode tun        # 切换到 TUN（远程 SSH 默认拒绝）
mihomo-tui mode mixed      # 切回 7890 mixed-port
```

`mixed` 模式通过 `127.0.0.1:7890` 提供 HTTP 和 SOCKS5 代理，需要应用显式使用代理端口。`tun` 模式启用系统透明代理并同时保留 7890 端口，通常不需要设置代理环境变量，但仍兼容需要显式代理的程序。远程 SSH 会话切换 TUN 可能导致断联，建议使用云控制台或第二条管理链路；确需从 SSH 操作时显式使用 `--allow-ssh-risk`。

让终端流量走代理：

```bash
export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890
```

完整命令和更新订阅说明见 [USAGE.md](USAGE.md)。

## 配置约定

`mihomo-tui` 支持以下环境变量覆盖默认值：

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
- `setup-wizard.py` — 安装向导、订阅输入和软件包生成
- `vendor/` — 随包提供的 PyYAML 及许可证
- `test-setup.py` — YAML 导入隔离测试
- `CHANGELOG.md` — 版本记录与已知限制
- `INSTALL.md` — 在线与离线安装文档
- `test-mnode.py` — 隔离回归测试
- `mihomo-tui` — 默认打开菜单的新入口
- `mnode` — 原有 CLI 与兼容入口
- `build-config.py` — 把 SS/Clash YAML 节点转换成受控 mihomo 配置
- `USAGE.md` — 完整中文操作文档

## 安全说明

- 默认所有端口只监听 `127.0.0.1`，不对外暴露。
- **订阅链接、`sub.b64`、生成的 `config.yaml` 都含有凭据，请勿提交到仓库**（见 `.gitignore`）。
- 若开放 `allow-lan` 或改动 API 监听地址，务必先给 API 设置 `secret`。

## License

MIT

### 订阅下载兼容性

订阅链接请求使用 `User-Agent: clash.meta`，安装向导与管理菜单一致；请求未主动使用本地 mixed，但会遵循进程的系统代理环境变量。旧版使用 Python 默认的 `Python-urllib/3.x`。

获取失败会区分 HTTP 状态、DNS、TLS 证书和超时；HTTP 200 的 HTML 登录页/防护页也会提示。401/403 可能涉及凭据、IP 或 UA 限制，429 表示限流；修改 UA 无法解决所有问题。请检查链接有效性、服务器直连能力、系统时间与 CA 证书，或在可访问的设备获取原文后粘贴。不要在排错时公开带 token 的订阅 URL。成功获取但格式解析失败属于另一阶段，例如 provider-only YAML 不在支持范围内。
