# 安装、离线部署与升级

支持运行 systemd 的 Debian/Ubuntu、RHEL 系 Linux，amd64（compatible 构建）和 arm64。内核固定 `v1.19.28`，不查询最新版本。目标服务器无需 Git。安装过程需要 root 及网络命名空间权限（`unshare --net`）；受限容器不适用。

## 获取完整项目文件

从本项目一个**包含安装器的已发布提交**获取下列文件，保持同一版本。`REV` 必须替换成该提交的完整 40 位 SHA；尚未发布的本地修改应直接复制整个文件集合，不能使用旧提交获取新文件。

```bash
mkdir -p ~/mnode-install
cd ~/mnode-install
REV=替换为包含本安装器的完整提交SHA
for file in install.sh install.py assets.json project-sha256.json mnode build-config.py mnode-tui.py README.md USAGE.md INSTALL.md; do
  curl -fL --connect-timeout 8 --max-time 45 \
    "https://cdn.jsdelivr.net/gh/esojourn/mnode@$REV/$file" -o "$file" || break
done
```

也可把域名换为 `testingcf.jsdelivr.net`、`gcore.jsdelivr.net`、`fastly.jsdelivr.net`，或从 `https://raw.githubusercontent.com/esojourn/mnode/$REV/文件名` 下载。安装器和校验清单应来自你信任的项目提交；摘要校验不能替代对安装器本身的信任。

`project-sha256.json` 记录本版项目文件摘要，`assets.json` 记录内核、数据库精确文件名、官方来源及可信 SHA-256。项目文件已完整上传时不访问项目 CDN；运行脚本缺失或损坏时，可加 `--project-ref "$REV"` 按上述 CDN 顺序和官方源补齐，仍必须匹配本地可信清单。离线模式始终禁止补下载。

## 依赖

```bash
# Debian / Ubuntu
sudo apt install bash python3 curl ca-certificates util-linux systemd sudo
# RHEL 系
sudo dnf install bash python3 curl ca-certificates util-linux systemd sudo
```

需要 Python 3.8+。脚本不会安装依赖或替换软件源。完全离线时，在相同发行版、版本和架构的联网环境准备依赖包及其递归依赖；使用干净的同版容器/虚拟机可避免遗漏已安装依赖。Debian 系可用 `apt-offline` 工作流，或在该环境的 apt 缓存中收集 `apt-get --download-only install …` 的全部 deb；RHEL 系安装 `dnf-plugins-core` 后使用 `dnf download --resolve --alldeps …` 收集 rpm。连同包目录上传，使用本地包源安装并先确认上述命令均可用。不要仅上传一个 python3 或 curl 包。

## 在线安装

先把本地 Shadowsocks 订阅放到 `~/mnode-install/sub.b64`（支持 base64 或明文 `ss://`），权限设为 600：

```bash
cd ~/mnode-install
chmod 600 sub.b64
sudo bash install.sh --subscription "$PWD/sub.b64"
mnode tui
```

有效本地资源优先；网络下载写入临时文件，摘要匹配才落盘。每个资源最多 8 个源、每源一次尝试、连接超时 8 秒、单次最多 45 秒、总预算 180 秒。内核依次尝试 ghfast.top、gh-proxy.com、gh-proxy.org、GitHub 官方。可重复添加最多 4 个 `--mirror https://代理域名`，代理 URL 格式为 `代理域名/完整GitHub附件URL`。

数据库固定提交 `1234686cec4ff41207931ee441a13ea4e26ebf13`，依次使用 cdn.jsdelivr.net、testingcf、gcore、fastly、官方 raw。jsDelivr 的 `/gh/` 用于仓库文件，不能作为 Release 附件的通用代理；多个域名也不是独立服务体系。参见 [jsDelivr 官方说明](https://github.com/jsdelivr/jsdelivr#github)。

首次安装生成 mixed 配置，以候选内核和本地数据库在禁网命名空间内验证；配置明确关闭 GeoIP 自动更新。安装完成不会启动服务或开启自启，需要时执行 `mnode on`。

## 离线准备与上传

在联网电脑上获取完整项目文件后执行（可为另一架构准备）：

```bash
bash install.sh --download-only --arch amd64 --assets-dir ./assets
# ARM64 目标改用 --arch arm64
```

上传目录统一为：

```text
~/mnode-install/
  install.sh
  install.py
  assets.json
  project-sha256.json
  mnode
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
| mnode | 上述固定提交项目地址 | `/usr/local/bin/mnode` |
| build-config.py、mnode-tui.py | 上述固定提交项目地址 | `/etc/mihomo/` |
| sub.b64 | 自行向订阅服务获取，不提供公共 URL | `/etc/mihomo/sub.b64`，600 |
| config.yaml | 安装时本地生成 | `/etc/mihomo/config.yaml`，600 |
| install.sh、install.py、两份清单 | 上述固定提交项目地址 | 留在上传目录，供升级使用 |
| mihomo.service | 首次安装本地生成 | `/etc/systemd/system/mihomo.service` |

```bash
scp -r ~/mnode-install user@server:~/
ssh user@server
cd ~/mnode-install
sudo bash install.sh --offline --assets-dir "$PWD/assets" --subscription "$PWD/sub.b64"
```

`--offline` 不下载、不查询版本；缺失或损坏资源会输出补齐路径、官方地址、SHA-256。校验失败时重新传输正确版本，不修改清单来迁就错误文件。已有配置如果依赖额外数据库或远程 provider，必须事先准备本地资源；禁网验证失败会终止安装。

## 重复安装、升级和恢复

普通安装只补齐缺失组件，保留现有配置、订阅、服务与已有内核。安装器要求现有服务有效的 ExecStart 为 `/usr/local/bin/mihomo -d /etc/mihomo -f /etc/mihomo/config.yaml`；其他参数或路径提前拒绝。升级仍固定到本版本清单，不自动追踪上游。

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
