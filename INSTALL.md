# 安装、离线部署与升级

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


支持运行 systemd 的 Debian/Ubuntu、RHEL 系 Linux，amd64（compatible 构建）和 arm64。内核固定 `v1.19.28`，不查询最新版本。目标服务器无需 Git。安装过程需要 root 及网络命名空间权限（`unshare --net`）；受限容器不适用。

## 获取完整项目文件

使用同一版本的完整项目压缩包或完整 Git checkout，保留 `vendor/` 目录。不要只下载入口脚本：项目校验清单包含安装器、运行脚本和 YAML 组件。

联网机器可以使用上面的 `--bundle` 命令生成上传包。目标服务器无需 Git：

```bash
sha256sum -c mihomo-tui-amd64.tar.gz.sha256
tar -xzf mihomo-tui-amd64.tar.gz
cd mihomo-tui
sudo bash install.sh
```

向导中选择严格离线即可禁止安装资源下载；若系统依赖缺失，入口会先询问是否调用包管理器，完全离线环境应取消并补齐依赖。在线模式优先使用校验通过的本地资源。

安装器及其摘要清单必须来自可信来源。现有 `--project-ref` 仅用于补齐可下载的运行脚本，不能替代完整软件包，尤其不能自动补齐 `vendor/`。

## 依赖

```bash
# Debian / Ubuntu
sudo apt install bash python3 curl ca-certificates util-linux systemd sudo
# RHEL 系
sudo dnf install bash python3 curl ca-certificates util-linux systemd sudo
```

需要 Python 3.8+。向导会检测 Python、curl、util-linux，确认后使用现有 apt/dnf 安装缺项；带参数的非交互安装只检测依赖。不更换软件源，不能自动补齐 systemd 或所有 CA 环境问题。完全离线时，在相同发行版、版本和架构的联网环境准备依赖包及其递归依赖；使用干净的同版容器/虚拟机可避免遗漏已安装依赖。Debian 系可用 `apt-offline` 工作流，或在该环境的 apt 缓存中收集 `apt-get --download-only install …` 的全部 deb；RHEL 系安装 `dnf-plugins-core` 后使用 `dnf download --resolve --alldeps …` 收集 rpm。连同包目录上传，使用本地包源安装并先确认上述命令均可用。不要仅上传一个 python3 或 curl 包。

## 在线安装

先把本地订阅放到 `~/mihomo-tui-install/sub.b64`（支持 Base64、明文 `ss://` 或含内嵌节点的 Clash YAML），权限设为 600：

```bash
cd ~/mihomo-tui-install
chmod 600 sub.b64
sudo bash install.sh --subscription "$PWD/sub.b64"
mihomo-tui tui
```

有效本地资源优先；网络下载写入临时文件，摘要匹配才落盘。每个资源最多 8 个源、每源一次尝试、连接超时 8 秒、单次最多 45 秒、总预算 180 秒。内核依次尝试 ghfast.top、gh-proxy.com、gh-proxy.org、GitHub 官方。可重复添加最多 4 个 `--mirror https://代理域名`，代理 URL 格式为 `代理域名/完整GitHub附件URL`。

数据库固定提交 `1234686cec4ff41207931ee441a13ea4e26ebf13`，依次使用 cdn.jsdelivr.net、testingcf、gcore、fastly、官方 raw。jsDelivr 的 `/gh/` 用于仓库文件，不能作为 Release 附件的通用代理；多个域名也不是独立服务体系。参见 [jsDelivr 官方说明](https://github.com/jsdelivr/jsdelivr#github)。

首次安装生成 mixed 配置，以候选内核和本地数据库在禁网命名空间内验证；配置明确关闭 GeoIP 自动更新。上述带参数安装不会启动服务或开启自启。无参数向导在安装后单独询问是否启动并检查代理 HTTPS，以及是否启用自启。

## 离线准备与上传

在联网电脑上获取完整项目文件后执行（可为另一架构准备）：

```bash
bash install.sh --download-only --arch amd64 --assets-dir ./assets
# ARM64 目标改用 --arch arm64
```

上传目录统一为：

```text
~/mihomo-tui-install/
  install.sh
  install.py
  setup-wizard.py
  vendor/                         # YAML 解析组件及许可证
  assets.json
  project-sha256.json
  mihomo-tui
  build-config.py
  mnode-tui.py
  README.md / USAGE.md / INSTALL.md
  sub.b64                         # 私有订阅，不进入仓库
  assets/
    mihomo-linux-amd64-compatible-v1.19.28.gz
    geoip.metadb
```

ARM64 对应 `mihomo-linux-arm64-v1.19.28.gz`。资源的完整地址、摘要都在 [assets.json](assets.json)：

| 资源 | 下载位置 | 最终路径 |
|---|---|---|
| amd64 内核压缩包 | [官方 Release](https://github.com/MetaCubeX/mihomo/releases/download/v1.19.28/mihomo-linux-amd64-compatible-v1.19.28.gz) | `/usr/local/bin/mihomo`（解压后） |
| arm64 内核压缩包 | [官方 Release](https://github.com/MetaCubeX/mihomo/releases/download/v1.19.28/mihomo-linux-arm64-v1.19.28.gz) | `/usr/local/bin/mihomo`（解压后） |
| GeoIP | [固定官方提交](https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/1234686cec4ff41207931ee441a13ea4e26ebf13/geoip.metadb) | `/etc/mihomo/geoip.metadb` |
| mihomo-tui | 上述固定提交项目地址 | `/usr/local/bin/mihomo-tui` |
| build-config.py、mnode-tui.py、setup-wizard.py、vendor/ | 上述固定提交项目地址 | `/etc/mihomo/` |
| sub.b64 | 自行向订阅服务获取，不提供公共 URL | `/etc/mihomo/sub.b64`，600 |
| config.yaml | 安装时本地生成 | `/etc/mihomo/config.yaml`，600 |
| install.sh、install.py、两份清单 | 上述固定提交项目地址 | 留在上传目录，供升级使用 |
| mihomo.service | 首次安装本地生成 | `/etc/systemd/system/mihomo.service` |

```bash
scp -r ~/mihomo-tui-install user@server:~/
ssh user@server
cd ~/mihomo-tui-install
sudo bash install.sh --offline --assets-dir "$PWD/assets" --subscription "$PWD/sub.b64"
```

`--offline` 不下载、不查询版本；缺失或损坏资源会输出补齐路径、官方地址、SHA-256。校验失败时重新传输正确版本，不修改清单来迁就错误文件。已有配置如果依赖额外数据库或远程 provider，必须事先准备本地资源；禁网验证失败会终止安装。

## 重复安装、升级和恢复

普通安装只补齐缺失组件，保留现有配置、订阅、服务与已有内核。安装器支持现有服务 ExecStart 为 `/usr/local/bin/mihomo -d /etc/mihomo`，可选显式添加 `-f /etc/mihomo/config.yaml`；其他参数或路径提前拒绝。升级仍固定到本版本清单，不自动追踪上游。

```bash
sudo bash install.sh --upgrade --assets-dir "$PWD/assets"
sudo bash install.sh --upgrade --offline --assets-dir "$PWD/assets"
# 自定义 API/secret 时，升级健康检查使用相同环境设置
sudo --preserve-env=MIHOMO_API,MIHOMO_SECRET bash install.sh --upgrade
```

安装与 CLI 配置修改共用 `/etc/mihomo/.mnode.lock`。验证成功后备份，再逐文件原子替换。运行中的服务会重启并检查 API；失败恢复文件并尝试恢复原运行状态。停止的服务保持停止。升级不重建现有配置和订阅，也不改开机启动设置。

备份位于 `/etc/mihomo/backup-*/`，`receipt.json` 中记录每个原路径、备份编号以及原服务状态。若自动恢复也失败，先检查 `systemctl status mihomo` 和日志；在持有 `.mnode.lock` 的维护窗口中按清单恢复文件（`saved: null` 表示原文件不存在），执行 `systemctl daemon-reload`，再按记录启动或停止服务。备份仅 root 可访问，可能包含敏感数据，请妥善保管。突然断电/强制 SIGKILL 不属于自动异常回滚范围，可按回执恢复。

## 验证记录与范围

2026-11-02：本轮从 GitHub 官方完整下载 amd64 compatible v1.19.28，SHA-256 与官方 Release API digest 一致；完整下载上述固定 GeoIP，摘要为 `c54a1704ee3e245bec1cb65c2e2948311eeee532e2ea1eed09322425d28775be`。真实 amd64 内核通过 synthetic 订阅生成的 mixed/TUN 配置检查。ARM64 附件也已完整下载，SHA-256 与官方 Release API digest 一致；本轮未在 ARM 主机运行。

前序方案报告 cdn/fastly/gcore/testingcf 固定 GeoIP 与官方一致，gh-proxy.org/ghfast.top/gh-proxy.com 的内核完整下载通过；其测试日期与原始日志未随方案提供，不能当作本轮复测。ghproxy.net 超时、kkgithub.com 404，未放入默认来源池。所有来源仍需在目标网络验证。

运行 `python3 test-mnode.py` 执行隔离回归测试，使用模拟网络命令和 systemd，不修改开发机服务或路由。真实 systemd 重启、发行版依赖安装、网络命名空间权限及 TUN 路由仍应在目标同版虚拟机验收。

## 当前实现边界

- 来源探测按顺序对真实资源发送限时 Range 请求，显示耗时和速率。某些不支持 Range 的源可能被判失败；这不是长期稳定性保证。现在可按编号选择优先 Release 镜像或输入 HTTPS 根地址；数据库沿用固定回退顺序。
- 向导首次安装检查 7890/9090 端口；确认启动后检查 API 和代理 HTTPS，可进一步测试 GitHub。尚未实现低并发自动测速选节点，也不会自动切换后续资源下载路径；可在管理菜单手动测速、选节点。
- YAML 仅导入内嵌节点，拒绝重复名称、远程 provider-only 配置以及外部证书文件/拨号依赖。不会保留供应商规则或分组。链接输入不持久保存、不提供定时刷新；终端输入可见，请注意终端录屏。
- 参数 `--wizard` 与 `--bundle` 应作为第一个参数使用。向导自身不接受 `--offline` 等安装参数；严格离线通过菜单选择，自动化则使用原有带参数入口。
- 2026-11-03：22 项原有隔离测试、3 项新增 YAML 测试、语法检查与轻量包生成通过。尚未进行新流程的真实生产服务器、ARM64 和完整离线虚拟机验收。

### 订阅下载兼容性

订阅链接请求使用 `User-Agent: clash.meta`，安装向导与管理菜单一致；请求未主动使用本地 mixed，但会遵循进程的系统代理环境变量。旧版使用 Python 默认的 `Python-urllib/3.x`。

获取失败会区分 HTTP 状态、DNS、TLS 证书和超时；HTTP 200 的 HTML 登录页/防护页也会提示。401/403 可能涉及凭据、IP 或 UA 限制，429 表示限流；修改 UA 无法解决所有问题。请检查链接有效性、服务器直连能力、系统时间与 CA 证书，或在可访问的设备获取原文后粘贴。不要在排错时公开带 token 的订阅 URL。成功获取但格式解析失败属于另一阶段，例如 provider-only YAML 不在支持范围内。

### 本次会话的代理环境

运行 `mihomo-tui`，选择 **12 设置/清除代理环境（命令提示）**，再选择设置或清除。菜单显示对应命令后退出，请在当前终端自行粘贴执行：

```bash
# 设置
export https_proxy=http://127.0.0.1:7890 http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890
# 清除
unset https_proxy http_proxy all_proxy
```

命令仅针对本次 Shell 会话及之后启动的子进程，不修改 `.bashrc` 或系统配置，不影响其他终端和已经运行的服务。菜单只显示提示，不执行命令，也不会启动 mihomo。清除仅移除上述三个小写变量，不恢复旧值，不修改大写代理变量或 `no_proxy`。选择 `0 返回` 则继续使用菜单。

### 设置代理后 API 不通或升级健康检查失败

控制 API 请求与安装器健康检查现在强制直连（`curl --noproxy '*'`），避免 `http_proxy`/`all_proxy` 等变量把本地 9090 请求送进 7890 代理。资源下载仍可使用代理环境。此策略同样适用于自定义 `MIHOMO_API` 地址。

旧版出现此问题时，先退出菜单，在当前终端执行：

```bash
unset https_proxy http_proxy all_proxy HTTPS_PROXY HTTP_PROXY ALL_PROXY
curl --noproxy '*' --max-time 3 http://127.0.0.1:9090/version
mnode status
```

直连仍失败时检查 `systemctl status mihomo --no-pager` 和 `journalctl -u mihomo -n 50 --no-pager`，确认服务监听和 API 配置；自定义 API 地址或 secret 时需使用对应设置。不要公开含凭据的日志或配置。直连成功后可再执行 `sudo bash install.sh --upgrade`，完整升级可能重启服务。

### 已有配置与服务的安装检查

向导检测已有配置后保留配置和订阅，直接调用安装后端，不会再次进入向导。取消安装或安装失败时不会继续打开管理菜单。镜像选择使用编号，只针对内核 Release；数据库 CDN 文件地址不能作为 Release 镜像。

测速和资源下载前先检查现有服务兼容性。若提示不兼容，请执行：

```bash
systemctl --no-pager cat mihomo
systemctl --no-pager --full show mihomo -p ExecStart -p FragmentPath -p DropInPaths
```

安装器支持 `ExecStart=/usr/local/bin/mihomo -d /etc/mihomo`，也支持显式添加 `-f /etc/mihomo/config.yaml`；两者读取同一配置，保留现有服务的资源限制、权限、重启和重载设置。其他路径、参数或 drop-in 覆盖需要先核对并规划迁移；不要直接删除旧服务或配置。普通安装仍只补缺失文件，更新已安装程序需 `--upgrade`。
