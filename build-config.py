#!/usr/bin/env python3
# Convert a base64 Shadowsocks subscription (SIP002 ss:// links) into a mihomo config.yaml
import base64, sys, urllib.parse, re

SUB = "/etc/mihomo/sub.b64"
OUT = "/etc/mihomo/config.yaml"

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
    # quote a yaml scalar safely
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"') + '"'

def main():
    with open(SUB) as f:
        raw = f.read()
    text = decode_sub(raw)
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
    if not nodes:
        print("ERROR: no nodes parsed", file=sys.stderr)
        sys.exit(1)
    names = [n["name"] for n in nodes]
    L = []
    L.append("mixed-port: 7890")
    L.append("allow-lan: false")
    L.append("mode: rule")
    L.append("log-level: info")
    L.append("ipv6: false")
    L.append("external-controller: 127.0.0.1:9090")
    L.append("secret: \"\"")
    L.append("")
    L.append("proxies:")
    for n in nodes:
        line = ("  - {name: %s, type: ss, server: %s, port: %d, cipher: %s, password: %s"
                % (yesc(n["name"]), yesc(n["server"]), n["port"], yesc(n["cipher"]), yesc(n["password"])))
        if n.get("plugin") == "obfs":
            po = n["plugin-opts"]
            line += ", plugin: obfs, plugin-opts: {mode: %s" % po.get("mode", "http")
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
    with open(OUT, "w") as f:
        f.write("\n".join(L) + "\n")
    print(f"OK: wrote {len(nodes)} nodes to {OUT}")

if __name__ == "__main__":
    main()
