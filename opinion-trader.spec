# -*- mode: python ; coding: utf-8 -*-
"""
Opinion Trader CLI PyInstaller 配置文件

这是一个预配置的 .spec 文件，可以直接用于打包:
    pyinstaller opinion-trader.spec

或者使用 build.py 脚本自动生成和打包。
"""

import sys
import os
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# 收集 opinion_clob_sdk 的所有子模块
hiddenimports = [
    'opinion_clob_sdk',
    'httpx',
    'httpx._transports',
    'httpx._transports.default',
    'pydantic',
    'websockets',
    'websockets.client',
    'websockets.server',
    'requests',
    'socks',
    'sockshandler',
    'json',
    'asyncio',
    'concurrent.futures',
]

# 添加 opinion_clob_sdk 的子模块
try:
    hiddenimports += collect_submodules('opinion_clob_sdk')
except Exception:
    pass

a = Analysis(
    ['trade.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'tkinter',
        'unittest',
        'test',
        'tests',
        'pytest',
        'setuptools',
        'pip',
        'wheel',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='opinion-trader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
