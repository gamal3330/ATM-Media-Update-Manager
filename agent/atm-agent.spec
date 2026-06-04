# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['atm_agent.py'],
    pathex=['.'],
    binaries=[],
    datas=[],
    hiddenimports=['api_client', 'backup_manager', 'cash_monitoring_module', 'checksum', 'config_manager', 'logger', 'media_update_module', 'module_runner', 'network_probe', 'path_policy', 'safe_zip', 'service', 'update_manager', 'pythoncom', 'pywintypes', 'servicemanager', 'win32event', 'win32service', 'win32serviceutil', 'win32timezone', 'xfs_cdm_diagnostics', 'xfs_cdm_reader'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='atm-agent',
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
