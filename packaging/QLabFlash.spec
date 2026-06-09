# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec: build a self-contained "QLab Flash.app".

Bundles the Python interpreter and PySide6 (Qt) inside the app, so the target
Mac needs nothing installed. Built in CI on an Apple Silicon macOS runner.
"""

import os

block_cipher = None

# Paths in a .spec are resolved relative to the spec file; this spec lives in
# packaging/, so reach up to the repo root for the real source files.
ROOT = os.path.abspath(os.path.join(SPECPATH, os.pardir))

a = Analysis(
    [os.path.join(ROOT, 'main.py')],
    pathex=[ROOT],
    binaries=[],
    datas=[(os.path.join(ROOT, 'assets', 'icon.png'), 'assets')],   # in-app window icon
    hiddenimports=['PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'],
    hookspath=[],
    runtime_hooks=[],
    excludes=['tkinter', 'PySide6.QtWebEngineCore', 'PySide6.QtQml',
              'PySide6.QtQuick', 'PySide6.Qt3DCore'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='QLab Flash',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    name='QLab Flash',
)

app = BUNDLE(
    coll,
    name='QLab Flash.app',
    icon=os.path.join(ROOT, 'assets', 'icon.icns'),
    bundle_identifier='com.jlmusicacademy.qlabflash',
    info_plist={
        'CFBundleName': 'QLab Flash',
        'CFBundleDisplayName': 'QLab Flash',
        'CFBundleShortVersionString': '1.0.0',
        'CFBundleVersion': '1.0.0',
        'NSHighResolutionCapable': True,
        'LSMinimumSystemVersion': '11.0',
    },
)
