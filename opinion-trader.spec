# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_all

datas = []
binaries = []
hiddenimports = ['opinion_trader', 'opinion_trader.app', 'opinion_trader.core.trader', 'opinion_trader.core.enhanced', 'opinion_trader.config.models', 'opinion_trader.config.loader', 'opinion_trader.services.services', 'opinion_trader.services.orderbook_manager', 'opinion_trader.display.display', 'opinion_trader.websocket.client', 'opinion_trader.utils.daemon', 'opinion_trader.utils.confirmation', 'opinion_trader.utils.helpers', 'opinion_clob_sdk', 'opinion_clob_sdk.chain', 'opinion_clob_sdk.chain.py_order_utils', 'opinion_clob_sdk.chain.py_order_utils.model', 'httpx', 'httpx._transports', 'httpx._transports.default', 'pydantic', 'websockets', 'websockets.client', 'requests', 'socks', 'sockshandler', 'json', 'asyncio', 'concurrent.futures', 'jaraco', 'jaraco.text', 'jaraco.functools', 'jaraco.context', 'questionary', 'prompt_toolkit', 'rich']
tmp_ret = collect_all('opinion_trader')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]
tmp_ret = collect_all('opinion_clob_sdk')
datas += tmp_ret[0]; binaries += tmp_ret[1]; hiddenimports += tmp_ret[2]


a = Analysis(
    ['__entry__.py'],
    pathex=['src'],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['tkinter', 'unittest', 'test', 'tests', 'pytest', 'pip', 'wheel'],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
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
