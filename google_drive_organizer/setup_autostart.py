"""
setup_autostart.py
ログイン時に local_organizer.py --watch を自動起動するサービスを
OS に登録・解除するセットアップスクリプト。

対応 OS:
  Linux  : systemd ユーザーサービス (~/.config/systemd/user/)
  macOS  : launchd LaunchAgent  (~/Library/LaunchAgents/)

使い方:
    # サービスを登録して即起動
    python setup_autostart.py install --root ~/GoogleDrive

    # OCR も有効にして登録
    python setup_autostart.py install --root ~/GoogleDrive --ocr

    # サービスの状態確認
    python setup_autostart.py status

    # サービスを停止・解除
    python setup_autostart.py uninstall
"""

from __future__ import annotations

import argparse
import logging
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import dedent

logger = logging.getLogger(__name__)

# サービス識別子
SERVICE_NAME = "drive-organizer"
MACOS_LABEL  = f"com.user.{SERVICE_NAME}"

# このスクリプトの場所 = local_organizer.py がある場所
SCRIPT_DIR = Path(__file__).resolve().parent
LOCAL_ORGANIZER = SCRIPT_DIR / "local_organizer.py"
LOG_DIR = SCRIPT_DIR / "logs"


# ================================================================== #
#  OS 判定
# ================================================================== #

def _is_linux() -> bool:
    return platform.system() == "Linux"

def _is_macos() -> bool:
    return platform.system() == "Darwin"

def _python_executable() -> str:
    """現在の Python 実行ファイルのパスを返す。"""
    return sys.executable


# ================================================================== #
#  Linux: systemd ユーザーサービス
# ================================================================== #

def _systemd_service_path() -> Path:
    return Path.home() / ".config" / "systemd" / "user" / f"{SERVICE_NAME}.service"


def _systemd_unit(root: Path, use_ocr: bool) -> str:
    """systemd サービスユニットファイルの内容を生成する。"""
    args = f"--root {root} --watch"
    if use_ocr:
        args += " --ocr"

    return dedent(f"""\
        [Unit]
        Description=Google Drive Inbox 自動整理 (drive-organizer)
        Documentation=file://{SCRIPT_DIR}/README.md
        After=network-online.target

        [Service]
        Type=simple
        ExecStart={_python_executable()} {LOCAL_ORGANIZER} {args}
        Restart=on-failure
        RestartSec=10
        StandardOutput=append:{LOG_DIR}/organizer.log
        StandardError=append:{LOG_DIR}/organizer.log

        [Install]
        WantedBy=default.target
    """)


def _systemd_install(root: Path, use_ocr: bool) -> None:
    """systemd ユーザーサービスを登録・起動する。"""
    service_path = _systemd_service_path()
    service_path.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    unit = _systemd_unit(root, use_ocr)
    service_path.write_text(unit)
    logger.info("サービスファイルを作成: %s", service_path)

    # systemd デーモンをリロード
    _run(["systemctl", "--user", "daemon-reload"])
    # ログイン時自動起動を有効化
    _run(["systemctl", "--user", "enable", SERVICE_NAME])
    # 今すぐ起動
    _run(["systemctl", "--user", "start", SERVICE_NAME])

    print(f"\n✓ サービスを登録・起動しました。")
    print(f"  監視対象 : {root / '00_Inbox'}")
    if use_ocr:
        print(f"  OCR      : 有効 (Tesseract)")
    print(f"\n  ログ     : {LOG_DIR}/organizer.log")
    print(f"  状態確認 : systemctl --user status {SERVICE_NAME}")
    print(f"  停止     : python setup_autostart.py uninstall")


def _systemd_uninstall() -> None:
    """systemd ユーザーサービスを停止・解除する。"""
    _run(["systemctl", "--user", "stop",    SERVICE_NAME], check=False)
    _run(["systemctl", "--user", "disable", SERVICE_NAME], check=False)
    service_path = _systemd_service_path()
    if service_path.exists():
        service_path.unlink()
        logger.info("サービスファイルを削除: %s", service_path)
    _run(["systemctl", "--user", "daemon-reload"])
    print(f"\n✓ サービスを停止・解除しました。")


def _systemd_status() -> None:
    """systemd サービスの状態を表示する。"""
    _run(["systemctl", "--user", "status", SERVICE_NAME], check=False)


# ================================================================== #
#  macOS: launchd LaunchAgent
# ================================================================== #

def _launchd_plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LABEL}.plist"


def _launchd_plist(root: Path, use_ocr: bool) -> str:
    """launchd plist ファイルの内容を生成する。"""
    args_xml = f"<string>{_python_executable()}</string>\n"
    args_xml += f"        <string>{LOCAL_ORGANIZER}</string>\n"
    args_xml += f"        <string>--root</string>\n"
    args_xml += f"        <string>{root}</string>\n"
    args_xml += f"        <string>--watch</string>"
    if use_ocr:
        args_xml += f"\n        <string>--ocr</string>"

    log_out = LOG_DIR / "organizer.log"
    log_err = LOG_DIR / "organizer_err.log"

    return dedent(f"""\
        <?xml version="1.0" encoding="UTF-8"?>
        <!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN"
            "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
        <plist version="1.0">
        <dict>
            <key>Label</key>
            <string>{MACOS_LABEL}</string>

            <key>ProgramArguments</key>
            <array>
                {args_xml}
            </array>

            <key>RunAtLoad</key>
            <true/>

            <key>KeepAlive</key>
            <true/>

            <key>StandardOutPath</key>
            <string>{log_out}</string>

            <key>StandardErrorPath</key>
            <string>{log_err}</string>

            <key>WorkingDirectory</key>
            <string>{SCRIPT_DIR}</string>
        </dict>
        </plist>
    """)


def _launchd_install(root: Path, use_ocr: bool) -> None:
    """launchd LaunchAgent を登録・起動する。"""
    plist_path = _launchd_plist_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    plist = _launchd_plist(root, use_ocr)
    plist_path.write_text(plist)
    logger.info("plist を作成: %s", plist_path)

    # 既存のエージェントをアンロード (エラーは無視)
    _run(["launchctl", "unload", str(plist_path)], check=False)
    # 登録・起動
    _run(["launchctl", "load", "-w", str(plist_path)])

    print(f"\n✓ LaunchAgent を登録・起動しました。")
    print(f"  監視対象 : {root / '00_Inbox'}")
    if use_ocr:
        print(f"  OCR      : 有効 (Tesseract)")
    print(f"\n  ログ     : {LOG_DIR}/organizer.log")
    print(f"  状態確認 : launchctl list {MACOS_LABEL}")
    print(f"  停止     : python setup_autostart.py uninstall")


def _launchd_uninstall() -> None:
    """launchd LaunchAgent を停止・解除する。"""
    plist_path = _launchd_plist_path()
    if plist_path.exists():
        _run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        logger.info("plist を削除: %s", plist_path)
    print(f"\n✓ LaunchAgent を停止・解除しました。")


def _launchd_status() -> None:
    """launchd エージェントの状態を表示する。"""
    _run(["launchctl", "list", MACOS_LABEL], check=False)


# ================================================================== #
#  共通ユーティリティ
# ================================================================== #

def _run(cmd: list[str], check: bool = True) -> None:
    """サブプロセスを実行する。失敗時は check=True なら例外を投げる。"""
    logger.debug("実行: %s", " ".join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)
        if check and result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, cmd)
    except FileNotFoundError:
        if check:
            raise RuntimeError(f"コマンドが見つかりません: {cmd[0]}")


def _check_prerequisites(root: Path, use_ocr: bool) -> None:
    """前提条件を確認する。問題があれば警告を表示。"""
    errors: list[str] = []
    warnings: list[str] = []

    # local_organizer.py の存在確認
    if not LOCAL_ORGANIZER.exists():
        errors.append(f"local_organizer.py が見つかりません: {LOCAL_ORGANIZER}")

    # ルートフォルダの確認
    inbox = root / "00_Inbox"
    if not root.exists():
        errors.append(f"--root に指定したパスが存在しません: {root}")
    elif not inbox.exists():
        warnings.append(f"00_Inbox フォルダが存在しません (初回実行時に作成されます): {inbox}")

    # watchdog の確認
    try:
        import watchdog
    except ImportError:
        errors.append("watchdog が未インストールです: pip install watchdog")

    # OCR の確認
    if use_ocr:
        try:
            import pdfplumber
        except ImportError:
            warnings.append("pdfplumber が未インストールです: pip install pdfplumber")
        try:
            import pytesseract
            pytesseract.get_tesseract_version()
        except Exception:
            warnings.append(
                "Tesseract が未インストールまたは設定が不完全です。\n"
                "  Ubuntu: sudo apt-get install tesseract-ocr tesseract-ocr-jpn\n"
                "  macOS : brew install tesseract tesseract-lang"
            )

    for w in warnings:
        print(f"  [警告] {w}")
    for e in errors:
        print(f"  [エラー] {e}")
    if errors:
        sys.exit(1)


# ================================================================== #
#  エントリーポイント
# ================================================================== #

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="drive-organizer の自動起動を OS に登録・解除する",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # install
    inst = sub.add_parser("install", help="自動起動を登録して即時起動する")
    inst.add_argument(
        "--root",
        required=True,
        metavar="DIR",
        help="Google Drive のローカル同期フォルダのルートパス",
    )
    inst.add_argument(
        "--ocr",
        action="store_true",
        help="ローカル Tesseract OCR フォールバックを有効にする",
    )

    # uninstall
    sub.add_parser("uninstall", help="自動起動を停止・解除する")

    # status
    sub.add_parser("status", help="サービスの状態を確認する")

    parser.add_argument("--verbose", "-v", action="store_true")
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.WARNING,
        format="%(levelname)s: %(message)s",
    )

    if args.command == "install":
        root = Path(args.root).expanduser().resolve()
        use_ocr = args.ocr
        print(f"前提条件を確認中...")
        _check_prerequisites(root, use_ocr)

        if _is_linux():
            _systemd_install(root, use_ocr)
        elif _is_macos():
            _launchd_install(root, use_ocr)
        else:
            print("Windows は現在未対応です。タスクスケジューラで以下を登録してください:")
            print(f"  {_python_executable()} {LOCAL_ORGANIZER} --root {root} --watch")
            sys.exit(1)

    elif args.command == "uninstall":
        if _is_linux():
            _systemd_uninstall()
        elif _is_macos():
            _launchd_uninstall()
        else:
            print("手動でタスクスケジューラからエントリを削除してください。")

    elif args.command == "status":
        if _is_linux():
            _systemd_status()
        elif _is_macos():
            _launchd_status()
        else:
            print("Windows のサービス状態は タスクスケジューラ で確認してください。")


if __name__ == "__main__":
    main()
