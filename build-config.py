#!/usr/bin/env python3
# Convert a base64 Shadowsocks subscription (SIP002 ss:// links) into a mihomo config.yaml
import argparse
from pathlib import Path
import base64, sys, urllib.parse, re, json, os

sys.path.insert(0, str(Path(__file__).resolve().parent / "vendor"))

SUB = "/etc/mihomo/sub.b64"
OUT = "/etc/mihomo/config.yaml"


def parse_args():
    p = argparse.ArgumentParser(description="Build a mihomo config from an ss:// subscription")
    p.add_argument("--mode", choices=("mixed", "tun"), default="mixed")
    p.add_argument("--subscription", default=SUB)
    p.add_argument("--output", default=OUT)
    return p.parse_args()

def b64pad(s):
    return s + "=" * (-len(s) % 4)

def decode_sub(raw):
    raw = raw.strip()
    # try base64 decode of whole blob; if it already looks like ss:// keep as-is
    if raw.startswith("ss://"):
        return raw
    return base64.b64decode(b64pad(raw)).decode("utf-8", "replace")

def parse_ss(line):
    # ss://BASE64(method:pass)@host:port/?plugin=...#name
    line = line.strip()
    if not line.startswith("ss://"):
        return None
    body = line[5:]
    # split fragment (name)
    name = ""
    if "#" in body:
        body, frag = body.split("#", 1)
        name = urllib.parse.unquote(frag).strip()
    # split plugin query
    query = ""
    if "?" in body:
        body, query = body.split("?", 1)
    body = body.rstrip("/")
    # body = BASE64userinfo@host:port
    if "@" not in body:
        return None
    userinfo, hostport = body.rsplit("@", 1)
    try:
        dec = base64.b64decode(b64pad(userinfo)).decode("utf-8", "replace")
        method, password = dec.split(":", 1)
    except Exception:
        return None
    host, port = hostport.rsplit(":", 1)
    node = {"name": name or f"{host}:{port}", "server": host,
            "port": int(port), "cipher": method, "password": password}
    # parse plugin
    q = urllib.parse.parse_qs(query)
    plugin = q.get("plugin", [""])[0]
    # plugin value can itself contain ';' separated opts
    if plugin:
        parts = plugin.split(";")
        pname = parts[0]
        opts = {}
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                opts[k] = v
        if pname in ("simple-obfs", "obfs-local", "obfs"):
            node["plugin"] = "obfs"
            po = {"mode": opts.get("obfs", "http")}
            if "obfs-host" in opts:
                po["host"] = opts["obfs-host"]
            node["plugin-opts"] = po
    return node

def yesc(s):
    return json.dumps(str(s), ensure_ascii=False)

def main():
    os.umask(0o077)
    opts = parse_args()
    with open(opts.subscription) as f:
        raw = f.read()
    yaml_nodes = None
    if not raw.strip().startswith("ss://"):
        import yaml
        try:
            doc = yaml.safe_load(raw)
            if isinstance(doc, dict):
                yaml_nodes = doc.get("proxies")
                if not isinstance(yaml_nodes, list) or not yaml_nodes:
                    raise ValueError("Clash YAML 需要内嵌 proxies；不支持远程 provider")
                def check_external(value):
                    if isinstance(value, dict):
                        if any(k in value for k in ('ca', 'certificate', 'private-key', 'dialer-proxy')):
                            raise ValueError("不支持节点外部文件或拨号依赖")
                        for v in value.values(): check_external(v)
                    elif isinstance(value, list):
                        for v in value: check_external(v)
                check_external(yaml_nodes)
                for node in yaml_nodes:
                    if not isinstance(node, dict) or not all(k in node for k in ("name", "type", "server", "port")):
                        raise ValueError("无效节点")
        except yaml.YAMLError as exc:
            raise ValueError("无效 YAML") from exc
    text = "" if yaml_nodes is not None else decode_sub(raw)
    nodes, seen = [], {}
    for line in text.replace("\r", "\n").split("\n"):
        if not line.strip():
            continue
        n = parse_ss(line)
        if not n:
            continue
        # dedupe names
        base = n["name"]
        i = seen.get(base, 0)
        if i:
            n["name"] = f"{base} #{i+1}"
        seen[base] = i + 1
        nodes.append(n)
    if yaml_nodes is not None:
        nodes = yaml_nodes
        names = [n['name'] for n in nodes]
        if len(set(names)) != len(names):
            raise ValueError("Clash 节点名称重复")
    if not nodes:
        print("ERROR: no nodes parsed", file=sys.stderr)
        sys.exit(1)
    names = [n["name"] for n in nodes]
    L = []
    L.append("mixed-port: 7890")
    if opts.mode == "tun":
        L.extend([
            "tun:",
            "  enable: true",
            "  stack: system",
            "  auto-route: true",
            "  auto-detect-interface: true",
            "  dns-hijack:",
            "    - any:53",
        ])
    L.extend(["geodata-mode: false", "geo-auto-update: false", "geox-url:", "  mmdb: \"\""])
    L.append("allow-lan: false")
    L.append("bind-address: 127.0.0.1")
    L.append("mode: rule")
    L.append("log-level: info")
    L.append("ipv6: false")
    L.append("external-controller: 127.0.0.1:9090")
    L.append("secret: \"\"")
    L.append("")
    L.append("proxies:")
    for n in nodes:
        if yaml_nodes is not None:
            L.append("  - " + json.dumps(n, ensure_ascii=False))
            continue
        line = ("  - {name: %s, type: ss, server: %s, port: %d, cipher: %s, password: %s"
                % (yesc(n["name"]), yesc(n["server"]), n["port"], yesc(n["cipher"]), yesc(n["password"])))
        if n.get("plugin") == "obfs":
            po = n["plugin-opts"]
            line += ", plugin: obfs, plugin-opts: {mode: %s" % yesc(po.get("mode", "http"))
            if "host" in po:
                line += ", host: %s" % yesc(po["host"])
            line += "}"
        line += "}"
        L.append(line)
    L.append("")
    L.append("proxy-groups:")
    L.append("  - name: PROXY")
    L.append("    type: select")
    L.append("    proxies:")
    L.append("      - AUTO")
    for nm in names:
        L.append("      - %s" % yesc(nm))
    L.append("  - name: AUTO")
    L.append("    type: url-test")
    L.append("    url: http://www.gstatic.com/generate_204")
    L.append("    interval: 300")
    L.append("    tolerance: 50")
    L.append("    proxies:")
    for nm in names:
        L.append("      - %s" % yesc(nm))
    L.append("")
    L.append("rules:")
    L.append("  - GEOIP,CN,DIRECT")
    L.append("  - MATCH,PROXY")
    with open(opts.output, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"OK: wrote {len(nodes)} nodes to {opts.output} ({opts.mode} mode)")

if __name__ == "__main__":
    main()
