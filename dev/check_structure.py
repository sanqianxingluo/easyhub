#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""结构检查：界面层的依赖方向不能反，页面之间不能互相 import。

层次（数字小的可以 import 数字大的，反之不行）：

    widgets 0  ->  poster 1  ->  page_* 2  ->  mainwindow 3  ->  ui 4（兼容入口）

跑法：python dev/check_structure.py
"""
from __future__ import annotations

import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, 'src')

LAYERS = {
    'widgets': 0,
    'poster': 1,
    'page_home': 2,
    'page_browse': 2,
    'page_detail': 2,
    'page_player': 2,
    'mainwindow': 3,
    'ui': 4,
}
# 这些是「基础设施」，任何层都可以用
INFRA = {'main', 'paths', 'theme', 'emby', 'library', 'libcache', 'servers',
         'player', 'setup_ui', 'settings_ui', 'version'}


def imports_of(path: str) -> list[tuple[str, str]]:
    """返回 [(模块名, 原文行)] —— 只看本仓库的模块。"""
    out = []
    with open(path, encoding='utf-8') as f:
        for line in f:
            m = re.match(r'\s*from\s+(\w+)\s+import\b', line)
            if m:
                mod = m.group(1)
            else:
                m = re.match(r'\s*import\s+(\w+)\s*$', line)
                if not m:
                    continue
                mod = m.group(1)
            if mod in LAYERS or mod in INFRA:
                out.append((mod, line.strip()))
    return out


def main() -> int:
    problems = []
    if not os.path.isdir(SRC):
        print('找不到 src/', file=sys.stderr)
        return 1

    for name in sorted(LAYERS):
        path = os.path.join(SRC, name + '.py')
        if not os.path.exists(path):
            problems.append(f'缺文件：src/{name}.py')
            continue
        my_layer = LAYERS[name]
        for mod, line in imports_of(path):
            if mod not in LAYERS:
                continue
            if LAYERS[mod] <= my_layer:
                continue
            problems.append(f'{name}.py（第 {my_layer} 层）反向 import 了 {mod}.py'
                            f'（第 {LAYERS[mod]} 层）：{line}')

    # 基础设施不能反向 import 界面层
    for name in sorted(INFRA):
        path = os.path.join(SRC, name + '.py')
        if not os.path.exists(path):
            continue
        for mod, line in imports_of(path):
            if mod in LAYERS and mod != 'ui':
                problems.append(f'{name}.py 是基础设施，不该 import 界面层 {mod}.py：{line}')

    # 除了 main.py / 兼容入口 ui.py / dev 脚本，没人该 import mainwindow
    for base, _dirs, files in os.walk(SRC):
        for f in files:
            if not f.endswith('.py') or f in ('mainwindow.py', 'main.py', 'ui.py'):
                continue
            for mod, line in imports_of(os.path.join(base, f)):
                if mod == 'mainwindow':
                    problems.append(f'{f} 直接 import 了 mainwindow：{line}')

    if problems:
        print('结构检查没通过：')
        for p in problems:
            print('  [!]', p)
        return 1

    print('结构检查通过：依赖方向单向，页面之间无互相 import。')
    for name in sorted(LAYERS, key=LAYERS.get):
        path = os.path.join(SRC, name + '.py')
        n = sum(1 for _ in open(path, encoding='utf-8')) if os.path.exists(path) else 0
        print(f'  L{LAYERS[name]}  {name + ".py":<18}{n:5d} 行')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
