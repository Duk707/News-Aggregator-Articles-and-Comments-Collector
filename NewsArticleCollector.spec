# -*- mode: python ; coding: utf-8 -*-

import os
import json
import playwright

block_cipher = None

# Dynamically resolve active Playwright browser revisions from installed browsers.json
pkg_dir = os.path.dirname(playwright.__file__)
browsers_json_path = os.path.join(pkg_dir, 'driver', 'package', 'browsers.json')

if not os.path.exists(browsers_json_path):
    raise FileNotFoundError(f"Playwright browsers.json not found at: {browsers_json_path}")

with open(browsers_json_path, 'r', encoding='utf-8') as f:
    browsers_config = json.load(f)

expected_folders = set()
for b in browsers_config.get('browsers', []):
    if b.get('installByDefault', False):
        name = b.get('name')
        rev = b.get('revision')
        if name and rev:
            expected_folders.add(f"{name}-{rev}")
            expected_folders.add(f"{name.replace('-', '_')}-{rev}")

# Locate Playwright browser binaries on host build system
user_ms_playwright = os.path.expanduser('~\\AppData\\Local\\ms-playwright')
datas = []
found_folders = set()

if not os.path.exists(user_ms_playwright):
    raise FileNotFoundError(
        f"Playwright browser storage directory not found at: {user_ms_playwright}\n"
        "Please run 'playwright install chromium' before building."
    )

for item in os.listdir(user_ms_playwright):
    full_p = os.path.join(user_ms_playwright, item)
    if os.path.isdir(full_p) and item in expected_folders:
        datas.append((full_p, os.path.join('ms-playwright', item)))
        found_folders.add(item)

# Verify required browser components exist before packaging
has_chromium = any(f.startswith('chromium-') for f in found_folders)
has_headless_shell = any(f.startswith('chromium_headless_shell-') or f.startswith('chromium-headless-shell-') for f in found_folders)

if not has_chromium or not has_headless_shell:
    raise RuntimeError(
        f"Missing required Playwright browser distributions in {user_ms_playwright}.\n"
        f"Expected folders: {expected_folders}\n"
        f"Found folders: {found_folders}\n"
        "Both standard Chromium and Chromium Headless Shell are required. "
        "Please run 'playwright install chromium' to ensure both are installed."
    )

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
    'src.discovery.legistar',
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
