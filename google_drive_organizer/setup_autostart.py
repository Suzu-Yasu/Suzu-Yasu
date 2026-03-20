"""
setup_autostart.py
ログイン時に local_organizer.py --watch を自動起動するサービスを
OS に登録・解除するセットアップスクリプト。

対応 OS:
  Linux  : systemd ユーザーサービス (~/.config/systemd/user/) + cron
  macOS  : launchd LaunchAgent  (~/Library/LaunchAgents/)

使い方:
    # INBOX への追加をリアルタイムで即時振り分け (watchdog 常駐)
    python setup_autostart.py install --root ~/GoogleDrive --watch

    # 毎日 05:00 に定時フルスキャン (cron/launchd)
    python setup_autostart.py install --root ~/GoogleDrive --schedule 05:00

    # 即時振り分け + 定時スキャンの両方 (推奨)
    python setup_autostart.py install --root ~/GoogleDrive --watch --schedule 05:00

    # OCR も有効にして登録
    python setup_autostart.py install --root ~/GoogleDrive --watch --ocr

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
MACOS_LABEL_SCHEDULE = f"com.user.{SERVICE_NAME}-schedule"

# crontab 識別コメント
CRON_COMMENT = "# drive-organizer-schedule"

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
#  スケジュールパーサ
# ================================================================== #

def _parse_schedule(schedule: str) -> tuple[int, int]:
    """'HH:MM' 形式をパースして (hour, minute) を返す。不正な場合は ValueError。"""
    parts = schedule.split(":")
    if len(parts) != 2:
        raise ValueError(f"スケジュール形式が不正です: {schedule!r} (例: 05:00)")
    try:
        hour, minute = int(parts[0]), int(parts[1])
    except ValueError:
        raise ValueError(f"スケジュール形式が不正です: {schedule!r} (例: 05:00)")
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        raise ValueError(f"時刻が範囲外です: {schedule!r} (hour: 0-23, minute: 0-59)")
    return hour, minute


# ================================================================== #
#  Linux: systemd ユーザーサービス (--watch)
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

    print(f"\n✓ 即時監視サービスを登録・起動しました。")
    print(f"  監視対象 : {root / '00_Inbox'}")
    if use_ocr:
        print(f"  OCR      : 有効 (Tesseract)")
    print(f"\n  ログ     : {LOG_DIR}/organizer.log")
    print(f"  状態確認 : systemctl --user status {SERVICE_NAME}")


def _systemd_uninstall() -> None:
    """systemd ユーザーサービスを停止・解除する。"""
    _run(["systemctl", "--user", "stop",    SERVICE_NAME], check=False)
    _run(["systemctl", "--user", "disable", SERVICE_NAME], check=False)
    service_path = _systemd_service_path()
    if service_path.exists():
        service_path.unlink()
        logger.info("サービスファイルを削除: %s", service_path)
    _run(["systemctl", "--user", "daemon-reload"])
    print(f"\n✓ 即時監視サービスを停止・解除しました。")


def _systemd_status() -> None:
    """systemd サービスの状態を表示する。"""
    _run(["systemctl", "--user", "status", SERVICE_NAME], check=False)


# ================================================================== #
#  Linux: cron (--schedule)
# ================================================================== #

def _cron_entry(root: Path, use_ocr: bool, hour: int, minute: int) -> str:
    """crontab に追加する1行を返す。"""
    args = f"--root {root}"
    if use_ocr:
        args += " --ocr"
    log = LOG_DIR / "organizer.log"
    return f"{minute} {hour} * * * {_python_executable()} {LOCAL_ORGANIZER} {args} >> {log} 2>&1"


def _cron_install(root: Path, use_ocr: bool, hour: int, minute: int) -> None:
    """既存の crontab に drive-organizer エントリを追加または上書き。"""
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    current = result.stdout if result.returncode == 0 else ""

    # 既存の drive-organizer エントリを削除
    lines = current.splitlines()
    new_lines: list[str] = []
    skip_next = False
    for line in lines:
        if skip_next:
            skip_next = False
            continue
        if line.strip() == CRON_COMMENT:
            skip_next = True
            continue
        new_lines.append(line)

    # 新しいエントリを追加
    new_lines.append(CRON_COMMENT)
    new_lines.append(_cron_entry(root, use_ocr, hour, minute))

    new_crontab = "\n".join(new_lines) + "\n"
    proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    if proc.returncode != 0:
        raise RuntimeError(f"crontab の更新に失敗しました: {proc.stderr}")
    logger.info("crontab にエントリを追加しました")

    print(f"\n✓ 定時実行 cron ジョブを登録しました。")
    print(f"  実行時刻 : 毎日 {hour:02d}:{minute:02d}")
    print(f"  ログ     : {LOG_DIR}/organizer.log")
    print(f"  確認     : crontab -l")


def _cron_uninstall() -> None:
    """crontab から drive-organizer エントリを削除。エントリがなければ何もしない。"""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        return

    lines = result.stdout.splitlines()
    new_lines: list[str] = []
    skip_next = False
    removed = False
    for line in lines:
        if skip_next:
            skip_next = False
            removed = True
            continue
        if line.strip() == CRON_COMMENT:
            skip_next = True
            continue
        new_lines.append(line)

    if not removed:
        return

    new_crontab = "\n".join(new_lines) + "\n"
    subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
    logger.info("crontab からエントリを削除しました")
    print(f"\n✓ 定時実行 cron ジョブを解除しました。")


def _cron_status() -> None:
    """crontab の drive-organizer エントリを表示する。"""
    result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
    if result.returncode != 0:
        print("  cron: エントリなし")
        return
    found = False
    lines = result.stdout.splitlines()
    for i, line in enumerate(lines):
        if line.strip() == CRON_COMMENT and i + 1 < len(lines):
            print(f"  cron スケジュール: {lines[i + 1]}")
            found = True
    if not found:
        print("  cron: drive-organizer のエントリなし")


# ================================================================== #
#  macOS: launchd LaunchAgent (--watch)
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

    print(f"\n✓ 即時監視 LaunchAgent を登録・起動しました。")
    print(f"  監視対象 : {root / '00_Inbox'}")
    if use_ocr:
        print(f"  OCR      : 有効 (Tesseract)")
    print(f"\n  ログ     : {LOG_DIR}/organizer.log")
    print(f"  状態確認 : launchctl list {MACOS_LABEL}")


def _launchd_uninstall() -> None:
    """launchd LaunchAgent を停止・解除する。"""
    plist_path = _launchd_plist_path()
    if plist_path.exists():
        _run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        logger.info("plist を削除: %s", plist_path)
        print(f"\n✓ 即時監視 LaunchAgent を停止・解除しました。")


def _launchd_status() -> None:
    """launchd エージェントの状態を表示する。"""
    _run(["launchctl", "list", MACOS_LABEL], check=False)


# ================================================================== #
#  macOS: launchd 定時実行 LaunchAgent (--schedule)
# ================================================================== #

def _launchd_plist_schedule_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MACOS_LABEL_SCHEDULE}.plist"


def _launchd_plist_schedule(root: Path, use_ocr: bool, hour: int, minute: int) -> str:
    """StartCalendarInterval を使った launchd plist を生成する。"""
    args_xml = f"<string>{_python_executable()}</string>\n"
    args_xml += f"        <string>{LOCAL_ORGANIZER}</string>\n"
    args_xml += f"        <string>--root</string>\n"
    args_xml += f"        <string>{root}</string>"
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
            <string>{MACOS_LABEL_SCHEDULE}</string>

            <key>ProgramArguments</key>
            <array>
                {args_xml}
            </array>

            <key>StartCalendarInterval</key>
            <dict>
                <key>Hour</key>
                <integer>{hour}</integer>
                <key>Minute</key>
                <integer>{minute}</integer>
            </dict>

            <key>StandardOutPath</key>
            <string>{log_out}</string>

            <key>StandardErrorPath</key>
            <string>{log_err}</string>

            <key>WorkingDirectory</key>
            <string>{SCRIPT_DIR}</string>
        </dict>
        </plist>
    """)


def _launchd_schedule_install(root: Path, use_ocr: bool, hour: int, minute: int) -> None:
    """定時実行 launchd LaunchAgent を登録する。"""
    plist_path = _launchd_plist_schedule_path()
    plist_path.parent.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    plist = _launchd_plist_schedule(root, use_ocr, hour, minute)
    plist_path.write_text(plist)
    logger.info("定時実行 plist を作成: %s", plist_path)

    _run(["launchctl", "unload", str(plist_path)], check=False)
    _run(["launchctl", "load", "-w", str(plist_path)])

    print(f"\n✓ 定時実行 LaunchAgent を登録しました。")
    print(f"  実行時刻 : 毎日 {hour:02d}:{minute:02d}")
    print(f"  ログ     : {LOG_DIR}/organizer.log")
    print(f"  状態確認 : launchctl list {MACOS_LABEL_SCHEDULE}")


def _launchd_schedule_uninstall() -> None:
    """定時実行 launchd LaunchAgent を停止・解除する。"""
    plist_path = _launchd_plist_schedule_path()
    if plist_path.exists():
        _run(["launchctl", "unload", str(plist_path)], check=False)
        plist_path.unlink()
        logger.info("定時実行 plist を削除: %s", plist_path)
        print(f"\n✓ 定時実行 LaunchAgent を停止・解除しました。")


def _launchd_schedule_status() -> None:
    """定時実行 launchd エージェントの状態を表示する。"""
    _run(["launchctl", "list", MACOS_LABEL_SCHEDULE], check=False)


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


def _check_prerequisites(root: Path, use_ocr: bool, use_watch: bool = True) -> None:
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

    # watchdog の確認 (--watch モードのみ必要)
    if use_watch:
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
        epilog=dedent("""\
            使用例:
              INBOX への追加をリアルタイム即時振り分け:
                python setup_autostart.py install --root ~/GoogleDrive --watch

              毎日 05:00 に定時フルスキャン:
                python setup_autostart.py install --root ~/GoogleDrive --schedule 05:00

              即時振り分け + 定時スキャン (推奨):
                python setup_autostart.py install --root ~/GoogleDrive --watch --schedule 05:00
        """),
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
        "--watch",
        action="store_true",
        help="INBOX へのファイル追加をリアルタイムで即時振り分け (watchdog 常駐)",
    )
    inst.add_argument(
        "--schedule",
        metavar="HH:MM",
        help="指定時刻に毎日定時フルスキャンを実行 (例: --schedule 05:00)",
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
        use_watch = args.watch
        schedule = args.schedule

        if not use_watch and not schedule:
            print("エラー: --watch または --schedule (あるいは両方) を指定してください。\n")
            print("  INBOX への追加をリアルタイム即時振り分け:")
            print(f"    python setup_autostart.py install --root {root} --watch")
            print("  毎日 05:00 に定時フルスキャン:")
            print(f"    python setup_autostart.py install --root {root} --schedule 05:00")
            print("  即時振り分け + 定時スキャン (推奨):")
            print(f"    python setup_autostart.py install --root {root} --watch --schedule 05:00")
            sys.exit(1)

        sched_hour, sched_minute = None, None
        if schedule:
            try:
                sched_hour, sched_minute = _parse_schedule(schedule)
            except ValueError as e:
                print(f"エラー: {e}")
                sys.exit(1)

        print(f"前提条件を確認中...")
        _check_prerequisites(root, use_ocr, use_watch=use_watch)

        if _is_linux():
            if use_watch:
                _systemd_install(root, use_ocr)
            if schedule:
                _cron_install(root, use_ocr, sched_hour, sched_minute)
        elif _is_macos():
            if use_watch:
                _launchd_install(root, use_ocr)
            if schedule:
                _launchd_schedule_install(root, use_ocr, sched_hour, sched_minute)
        else:
            cmds = []
            if use_watch:
                cmds.append(f"{_python_executable()} {LOCAL_ORGANIZER} --root {root} --watch")
            if schedule:
                cmds.append(f"タスクスケジューラで毎日 {sched_hour:02d}:{sched_minute:02d} に実行:")
                cmds.append(f"  {_python_executable()} {LOCAL_ORGANIZER} --root {root}")
            print("Windows は現在未対応です。以下を参考に手動で登録してください:")
            for cmd in cmds:
                print(f"  {cmd}")
            sys.exit(1)

        print(f"\n  停止     : python setup_autostart.py uninstall")

    elif args.command == "uninstall":
        if _is_linux():
            _systemd_uninstall()
            _cron_uninstall()
        elif _is_macos():
            _launchd_uninstall()
            _launchd_schedule_uninstall()
        else:
            print("手動でタスクスケジューラからエントリを削除してください。")

    elif args.command == "status":
        if _is_linux():
            _systemd_status()
            _cron_status()
        elif _is_macos():
            _launchd_status()
            _launchd_schedule_status()
        else:
            print("Windows のサービス状態は タスクスケジューラ で確認してください。")


if __name__ == "__main__":
    main()
