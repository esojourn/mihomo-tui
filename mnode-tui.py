#!/usr/bin/env python3
"""数字菜单；所有修改均交给 mnode 的验证、锁与回滚流程。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile


class Menu:
    def __init__(self, command):
        self.command = str(Path(command).resolve())
        self.group = os.environ.get('MIHOMO_GROUP', 'PROXY')

    def run(self, *args, capture=False, stdin=None):
        env = dict(os.environ, MIHOMO_GROUP=self.group)
        print('正在执行…', flush=True)
        result = subprocess.run([self.command, *args], env=env, stdin=stdin,
                                stdout=subprocess.PIPE if capture else None,
                                text=True)
        if result.returncode:
            print(f'操作失败（退出码 {result.returncode}），请检查上方原因。')
            return None
        if capture:
            try:
                return json.loads(result.stdout)
            except ValueError:
                print('API 返回的数据格式无效。')
        return result.returncode

    def nodes(self):
        data = self.run('list', self.group, '--json', capture=True)
        if data is None:
            return
        names = data.get('all', [])
        filtered, page = names, 0
        while True:
            print(f'\n[{self.group}] 当前: {data.get("now", "?")}  页 {page + 1}')
            for i, name in enumerate(filtered[page * 15:(page + 1) * 15], page * 15 + 1):
                print(f'{i}. {"*" if name == data.get("now") else " "} {name}')
            value = input('编号切换；n 下一页；p 上一页；f 筛选；s 按完整名称；0 返回: ').strip()
            if value == '0':
                return
            if value == 'n':
                page = min(page + 1, max(0, (len(filtered) - 1) // 15))
            elif value == 'p':
                page = max(0, page - 1)
            elif value == 'f':
                query = input('名称包含（空则全部）: ')
                filtered = [name for name in names if query.casefold() in name.casefold()]
                page = 0
            else:
                if value == 's':
                    name = input('完整名称（空则取消）: ')
                    if not name:
                        continue
                elif value.isdecimal() and 1 <= int(value) <= len(filtered):
                    name = filtered[int(value) - 1]
                else:
                    print('输入无效。')
                    continue
                if self.run('use', '--name', name, '-g', self.group) == 0:
                    data['now'] = name

    def groups(self):
        data = self.run('groups', '--json', capture=True)
        if data is None:
            return
        names = list(data)
        for i, name in enumerate(names, 1):
            print(f'{i}. {name} ({data[name].get("type")}) → {data[name].get("now", "")}')
        value = input('选择当前操作组，0 返回: ').strip()
        if value.isdecimal() and 1 <= int(value) <= len(names):
            self.group = names[int(value) - 1]
        elif value != '0':
            print('输入无效。')

    def subscription(self):
        value = input('1 本地文件更新  2 粘贴订阅  3 现有订阅重建  4 订阅链接更新  0 返回: ').strip()
        if value == '1':
            name = input('文件路径（空则取消）: ')
            if name:
                # Open before elevation so sudo never needs access to the user's directory.
                with open(Path(name).expanduser()) as source:
                    self.run('update', stdin=source)
        elif value == '2':
            print('粘贴订阅，单独一行 . 结束；空内容取消。')
            with tempfile.TemporaryFile(mode='w+') as source:
                while True:
                    line = input()
                    if line == '.':
                        break
                    source.write(line + '\n')
                if source.tell():
                    source.seek(0)
                    self.run('update', stdin=source)
        elif value == '4':
            import importlib.util
            from pathlib import Path
            spec = importlib.util.spec_from_file_location('subscription_input', Path(__file__).resolve().parent / 'setup-wizard.py')
            helper = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(helper)
            try:
                data = helper.subscription('A')
                with tempfile.TemporaryFile() as source:
                    source.write(data)
                    source.seek(0)
                    self.run('update', stdin=source)
            except ValueError:
                print('订阅获取取消或失败。')
        elif value == '3':
            # Empty input requests rebuilding with the stored subscription.
            with open(os.devnull) as source:
                self.run('update', stdin=source)
        elif value != '0':
            print('输入无效。')

    def proxy_environment(self):
        value = input('1 设置代理环境  2 清除代理环境  0 返回（仅本次 Shell 会话）: ').strip()
        if value == '0':
            return False
        if value not in ('1', '2'):
            print('输入无效。')
            return False
        action = 'set' if value == '1' else 'clear'
        command = ('export https_proxy=http://127.0.0.1:7890 '
                   'http_proxy=http://127.0.0.1:7890 all_proxy=socks5://127.0.0.1:7890'
                   if action == 'set' else 'unset https_proxy http_proxy all_proxy')
        print('即将退出菜单。请在当前终端粘贴并执行以下命令：')
        print(command)
        print('命令仅针对本次 Shell 会话及之后启动的子进程，不修改持久配置。')
        print('菜单未执行此命令，请自行粘贴执行。')
        return True

    def loop(self):
        while True:
            print(f'\n当前策略组: {self.group}\n1 服务状态  2 启动  3 停止\n4 策略组  5 节点列表/切换  6 选择 AUTO\n7 测速  8 接入模式  9 出口 IP\n10 订阅与配置  11 帮助  12 设置/清除代理环境（命令提示）  0 退出')
            value = input('请选择: ').strip()
            try:
                if value == '0':
                    return
                if value in ('1', '2', '3', '9', '11'):
                    self.run({'1': 'status', '2': 'on', '3': 'off', '9': 'ip', '11': 'help'}[value])
                elif value == '4':
                    self.groups()
                elif value == '5':
                    self.nodes()
                elif value == '6':
                    self.run('use', '--name', 'AUTO', '-g', self.group)
                elif value == '7':
                    self.run('test', self.group)
                elif value == '8':
                    self.run('mode')
                    mode = input('1 mixed  2 TUN  0 返回: ').strip()
                    if mode == '1':
                        self.run('mode', 'mixed')
                    elif mode == '2':
                        args = ['mode', 'tun']
                        if os.environ.get('SSH_CONNECTION') or os.environ.get('SSH_CLIENT'):
                            if input('TUN 自动路由可能导致 SSH 断联。输入 YES 确认（默认取消）: ') != 'YES':
                                continue
                            args.append('--allow-ssh-risk')
                        self.run(*args)
                    elif mode != '0':
                        print('输入无效。')
                elif value == '12':
                    if self.proxy_environment():
                        return
                elif value == '10':
                    self.subscription()
                else:
                    print('输入无效。')
            except OSError as exc:
                print(f'操作失败: {exc}')


def main():
    if not sys.stdin.isatty() or not sys.stdout.isatty():
        print('数字菜单需要交互终端，请使用 mnode help 查看 CLI。', file=sys.stderr)
        return 1
    try:
        Menu(sys.argv[1]).loop()
    except (EOFError, KeyboardInterrupt):
        print('\n已退出。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
