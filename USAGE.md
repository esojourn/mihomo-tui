# mihomo 操作文档

本机命令行下使用 mihomo 代理的完整说明。默认关闭，用时开、用完关。

## 一、概览

| 项目 | 值 |
|------|-----|
| 主程序 | `/usr/local/bin/mihomo`（v1.19.28, amd64-v3） |
| 配置目录 | `/etc/mihomo/` |
| 主配置 | `/etc/mihomo/config.yaml`（335 个节点） |
| 订阅原文 | `/etc/mihomo/sub.b64`（base64） |
| 转换脚本 | `/etc/mihomo/build-config.py` |
| 节点管理命令 | `/usr/local/bin/mnode` |
| systemd 服务 | `/etc/systemd/system/mihomo.service`（未开机自启） |
| 本地混合端口 | `127.0.0.1:7890`（http + socks5 共用） |
| 管理 API | `127.0.0.1:9090`（external-controller） |
| 节点类型 | Shadowsocks，`aes-128-gcm` + `simple-obfs`(http) 混淆 |
| 分流规则 | 国内直连（GEOIP,CN），其余走代理 |

## 二、开关代理

```bash
mnode on      # 启动 mihomo
mnode off     # 停止 mihomo
mnode status  # 查看运行状态和当前选中节点
```

服务不会开机自启，重启机器后需要 `mnode on` 手动开启。

## 三、选节点（CLI 版 zashboard）

```bash
mnode list              # 列出所有节点，带编号，* 是当前选中
mnode list | grep 香港   # 只看含"香港"的节点
mnode groups            # 列出所有策略组（PROXY / AUTO / GLOBAL）
mnode test              # 全部节点测速，按延迟从低到高排序
mnode use 2             # 切换到 2 号节点
mnode use AUTO          # 交给自动测速组，自动选最快
mnode ip                # 通过代理查看当前出口 IP（验证是否生效）
```

典型流程：`mnode test` 看哪个快 → `mnode list` 找编号 → `mnode use 编号`。

### 策略组说明

- **PROXY**：手动选择组，是实际生效的出口。里面第一项 `AUTO` 指向自动测速组。
- **AUTO**：url-test 组，每 300 秒自动挑延迟最低的节点。
- `mnode use` 默认操作 PROXY 组；`mnode use <名称> -g AUTO` 可指定其他组。

## 四、选择接入模式

```bash
mnode mode             # 查看当前模式
mnode mode mixed       # HTTP + SOCKS5，监听 127.0.0.1:7890
mnode mode tun         # TUN 透明代理，同时保留 7890
```

`mixed` 模式只代理显式使用 7890 的程序。`tun` 模式启用系统透明代理并通过 TUN 接口接管流量，同时保留 7890 端口，通常无需设置代理环境变量，但仍兼容需要显式代理配置的程序。两种模式都继续使用现有节点、策略组和分流规则；切换会先生成候选配置并通过 `mihomo -t` 验证，然后才替换正式配置。

> 在远程 SSH 会话中启用 TUN 可能改变路由并导致断联，因此默认拒绝。推荐通过云控制台或带外管理操作；确需继续时使用 `mnode mode tun --allow-ssh-risk`。tmux/screen 只能保留进程，不能防止网络断联。

## 五、让终端流量走 mixed 代理

mihomo 启动后，在需要走代理的终端里设置环境变量：

```bash
export https_proxy=http://127.0.0.1:7890
export http_proxy=http://127.0.0.1:7890
export all_proxy=socks5://127.0.0.1:7890
```

取消（恢复直连）：

```bash
unset https_proxy http_proxy all_proxy
```

验证：`curl https://ipinfo.io/json`，看返回的 IP/地区是否为所选节点。

> 提示：`git`、`npm`、`apt` 等大多数工具会自动读取这几个环境变量。个别工具需单独配置代理。

## 六、更新订阅

节点变动时更新。因为本服务器出口是国内 IP，订阅链接被 Cloudflare 拦截（返回 403），无法直接 curl 下载，需手动获取 base64 内容。

推荐用 `mnode update`，它会自动备份、生成、验证，失败自动回滚，服务在运行时还会自动重启使配置生效。

### 方式一：粘贴新订阅（最常用）

在能访问订阅的设备上打开订阅链接，复制返回的 base64 字符串，然后在服务器执行（粘贴内容后另起一行输入 `EOF`）：

```bash
mnode update <<'EOF'
（粘贴完整 base64，可多行）
EOF
```

### 方式二：先存文件再更新

```bash
cat > /tmp/newsub.b64 <<'EOF'
（粘贴完整 base64）
EOF
mnode update < /tmp/newsub.b64
```

### 方式三：仅重建配置（不换订阅）

改了 `build-config.py` 或想用现有订阅重新生成时：

```bash
mnode update
```

`mnode update` 的执行过程：
- 有新订阅内容时，先写入临时文件，不立即覆盖正式 `sub.b64`
- 使用临时订阅生成候选配置，并通过 `mihomo -t` 验证
- 验证成功后备份正式配置和订阅，再一起提交新版本
- 若服务正在运行则重启；重启失败时配置和订阅一起回滚并尝试恢复服务
- 若服务未运行则保留新配置，等下次 `mnode on` 生效

### 手动等价命令（排错备用）

```bash
python3 /etc/mihomo/build-config.py \
  && /usr/local/bin/mihomo -d /etc/mihomo -t \
  && systemctl restart mihomo
```

看到 `test is successful` 说明配置无误。

> 订阅链接自行保管，不要提交到代码仓库。

## 七、直接用 systemctl（mnode 的底层）

`mnode on/off` 等价于：

```bash
systemctl start mihomo      # 启动
systemctl stop mihomo       # 停止
systemctl status mihomo     # 详细状态
journalctl -u mihomo -f     # 实时日志（排错用）
```

## 八、直接调 API（mnode 的底层，排错备用）

```bash
# 查看某组当前节点和全部节点
curl -s http://127.0.0.1:9090/proxies/PROXY | python3 -m json.tool

# 手动切换节点
curl -X PUT http://127.0.0.1:9090/proxies/PROXY \
  -H "Content-Type: application/json" -d '{"name":"🇭🇰 香港 01丨1x HK"}'

# 对某组测速
curl -s "http://127.0.0.1:9090/group/PROXY/delay?url=http://www.gstatic.com/generate_204&timeout=5000"
```

## 九、常见问题

- **`mnode` 提示连不上 API**：mihomo 没运行，先 `mnode on`。
- **代理不通 / `mnode ip` 失败**：换个节点（`mnode test` 找延迟低的，`mnode use` 切换）。部分节点可能失效。
- **配置改坏了**：`mihomo -d /etc/mihomo -t` 会指出错误行；重跑第五节的生成命令可还原。
- **GeoIP 数据库**：位于 `/etc/mihomo/geoip.metadb`。若分流失效可从镜像重新下载：
  `curl -fsSL -o /etc/mihomo/geoip.metadb https://testingcf.jsdelivr.net/gh/MetaCubeX/meta-rules-dat@release/geoip.metadb`
- **想全局走代理（不分流）**：把 `config.yaml` 里 `rules:` 段改成只留 `- MATCH,PROXY`，或改 `build-config.py` 后重新生成。

## 十、安全说明

- 混合端口和管理 API 都只监听 `127.0.0.1`，仅本机可访问，未对外暴露。
- `allow-lan: false`，不接受局域网其他设备连接。
- 管理 API 无密码（`secret` 为空），因为只绑本地环回地址，风险可控。若日后开放 `allow-lan` 或改监听地址，务必先给 API 设置 `secret`。
