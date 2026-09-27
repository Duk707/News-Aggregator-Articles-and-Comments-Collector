# -*- mode: python ; coding: utf-8 -*-

import os
import glob

block_cipher = None

# Locate Playwright Chromium browser binaries on the host build system
user_ms_playwright = os.path.expanduser('~\\AppData\\Local\\ms-playwright')
datas = []

if os.path.exists(user_ms_playwright):
    for item in os.listdir(user_ms_playwright):
        full_p = os.path.join(user_ms_playwright, item)
        if os.path.isdir(full_p) and (item.startswith('chromium') or item.startswith('ffmpeg')):
            datas.append((full_p, os.path.join('ms-playwright', item)))

hidden_imports = [
    'playwright',
    'playwright.sync_api',
    'pydantic',
    'bs4',
    'requests',
    'urllib3',
    'tkinter',
    'tkinter.ttk',
    'xml.etree.ElementTree',
]

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=['pytest', 'unittest'],
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
    name='NewsArticleCollector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
