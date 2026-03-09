"""
organizer.py
Google Drive の 00_Inbox フォルダを自動整理するメインスクリプト。

使い方:
    python organizer.py               # 通常実行 (実際に移動)
    python organizer.py --dry-run     # ドライラン (移動せず確認のみ)
    python organizer.py --verbose     # 詳細ログ付き実行
"""

import argparse
import logging
import sys
from dataclasses import dataclass, field

from classifier import classify
from drive_client import DriveClient

# ------------------------------------------------------------------ #
#  定数
# ------------------------------------------------------------------ #

INBOX_FOLDER_NAME = "00_Inbox"

# ------------------------------------------------------------------ #
#  結果集計
# ------------------------------------------------------------------ #

@dataclass
class OrganizerStats:
    moved: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines = [
            "=" * 50,
            "  整理結果サマリー",
            "=" * 50,
            f"  移動済み : {len(self.moved)} ファイル",
            f"  スキップ : {len(self.skipped)} ファイル",
            f"  エラー   : {len(self.errors)} ファイル",
        ]
        if self.moved:
            lines.append("\n[移動済み]")
            lines.extend(f"  ✓ {name}" for name in self.moved)
        if self.skipped:
            lines.append("\n[スキップ (タグなし/判定不能)]")
            lines.extend(f"  - {name}" for name in self.skipped)
        if self.errors:
            lines.append("\n[エラー]")
            lines.extend(f"  ✗ {name}" for name in self.errors)
        lines.append("=" * 50)
        return "\n".join(lines)


# ------------------------------------------------------------------ #
#  コアロジック
# ------------------------------------------------------------------ #

def organize_inbox(
    client: DriveClient,
    dry_run: bool = False,
) -> OrganizerStats:
    """
    00_Inbox 内のファイルを分類して各フォルダに移動する。

    Parameters
    ----------
    client  : DriveClient
    dry_run : True の場合は移動を行わず、ログ出力のみ

    Returns
    -------
    OrganizerStats
    """
    stats = OrganizerStats()
    logger = logging.getLogger(__name__)

    # --- 1. Drive ルート ID を取得 ---
    root_id = client.get_root_id()
    logger.debug("Drive root id: %s", root_id)

    # --- 2. 00_Inbox フォルダを検索 ---
    inbox_id = client.find_folder(INBOX_FOLDER_NAME, root_id)
    if inbox_id is None:
        # Drive 全体からも検索
        inbox_id = client.find_folder_by_name_in_drive(INBOX_FOLDER_NAME)
    if inbox_id is None:
        logger.error("'%s' フォルダが見つかりません。", INBOX_FOLDER_NAME)
        sys.exit(1)
    logger.info("Inbox フォルダ発見 (id=%s)", inbox_id)

    # --- 3. Inbox 内のファイル一覧取得 ---
    files = client.list_files_in_folder(inbox_id)
    if not files:
        logger.info("Inbox にファイルがありません。")
        return stats

    logger.info("Inbox 内ファイル数: %d", len(files))

    # --- 4. 各ファイルを分類・移動 ---
    for f in files:
        file_id   = f["id"]
        file_name = f["name"]
        current_parent = inbox_id

        result = classify(file_name)
        logger.debug("'%s' → %s (%s)", file_name, result.target_path, result.reason)

        if not result.is_classified or not result.target_path:
            logger.info("SKIP '%s': %s", file_name, result.reason)
            stats.skipped.append(file_name)
            continue

        # --- 移動先フォルダ ID を解決 (なければ作成) ---
        try:
            target_folder_id = client.resolve_path(result.target_path, root_id=root_id)
        except Exception as e:
            logger.error("フォルダ解決エラー '%s': %s", file_name, e)
            stats.errors.append(file_name)
            continue

        dest_path_str = " / ".join(result.target_path)

        if dry_run:
            logger.info("[DRY-RUN] '%s'  →  %s", file_name, dest_path_str)
            stats.moved.append(f"{file_name}  →  {dest_path_str}")
            continue

        # --- 実際に移動 ---
        try:
            client.move_file(file_id, target_folder_id,
                             current_parent_id=current_parent)
            logger.info("MOVED '%s'  →  %s", file_name, dest_path_str)
            stats.moved.append(f"{file_name}  →  {dest_path_str}")
        except Exception as e:
            logger.error("移動エラー '%s': %s", file_name, e)
            stats.errors.append(file_name)

    return stats


# ------------------------------------------------------------------ #
#  エントリーポイント
# ------------------------------------------------------------------ #

def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Google Drive の 00_Inbox を自動整理します。",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="実際には移動せず、移動先の確認のみ行う",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="詳細なデバッグログを表示する",
    )
    parser.add_argument(
        "--credentials",
        default=None,
        help="credentials.json のパスを指定 (デフォルト: credentials/credentials.json)",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="token.json のパスを指定 (デフォルト: credentials/token.json)",
    )
    return parser


def main() -> None:
    args = build_arg_parser().parse_args()

    # ログ設定
    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger = logging.getLogger(__name__)
    if args.dry_run:
        logger.info("=== ドライランモード: ファイルは移動されません ===")

    # DriveClient 初期化
    kwargs: dict = {}
    if args.credentials:
        kwargs["credentials_file"] = args.credentials
    if args.token:
        kwargs["token_file"] = args.token

    client = DriveClient(**kwargs)

    # 整理実行
    stats = organize_inbox(client, dry_run=args.dry_run)

    # サマリー表示
    print(stats.summary())


if __name__ == "__main__":
    main()
