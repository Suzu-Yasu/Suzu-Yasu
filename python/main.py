"""
Notion → Google Drive 同期スクリプト

使い方:
  # ローカル実行（OAuth2 認証フロー）
  python main.py

  # GitHub Actions 等（サービスアカウント、環境変数で認証）
  GOOGLE_SERVICE_ACCOUNT_JSON=<base64> python main.py
"""

import base64
import json
import logging
import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from google.oauth2 import service_account
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials

from notion_client import NotionClient
from gdocs_client import GoogleDocsClient


# ────────────────────────────────────────────────────────────────────────────
# 定数
# ────────────────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/documents",
]

CREDENTIALS_FILE = Path(__file__).parent / "credentials.json"
TOKEN_FILE = Path(__file__).parent / "token.json"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# 設定読み込み
# ────────────────────────────────────────────────────────────────────────────

def load_config() -> dict:
    """環境変数から設定を読み込む。必須項目が欠けている場合はエラー。"""
    load_dotenv()

    api_key = os.getenv("NOTION_API_KEY", "").strip()
    db_ids_raw = os.getenv("NOTION_DATABASE_IDS", "").strip()
    folder_id = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "").strip()

    missing = []
    if not api_key:
        missing.append("NOTION_API_KEY")
    if not db_ids_raw:
        missing.append("NOTION_DATABASE_IDS")
    if not folder_id:
        missing.append("GOOGLE_DRIVE_FOLDER_ID")

    if missing:
        raise EnvironmentError(
            f"必須の環境変数が設定されていません: {', '.join(missing)}\n"
            f".env ファイルまたは環境変数を確認してください。"
        )

    database_ids = [id_.strip() for id_ in db_ids_raw.split(",") if id_.strip()]

    return {
        "notion_api_key": api_key,
        "database_ids": database_ids,
        "drive_folder_id": folder_id,
    }


# ────────────────────────────────────────────────────────────────────────────
# Google 認証
# ────────────────────────────────────────────────────────────────────────────

def get_google_credentials() -> Credentials:
    """
    Google 認証情報を取得する。

    優先順位:
      1. 環境変数 GOOGLE_SERVICE_ACCOUNT_JSON（base64 エンコードされた JSON）
         → GitHub Actions などの CI/CD 環境での使用を想定
      2. credentials.json + token.json（OAuth2 フロー）
         → ローカル実行での使用を想定
    """
    # 1. サービスアカウント（CI/CD）
    sa_json_b64 = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "").strip()
    if sa_json_b64:
        try:
            sa_json = base64.b64decode(sa_json_b64).decode("utf-8")
            sa_info = json.loads(sa_json)
            creds = service_account.Credentials.from_service_account_info(
                sa_info, scopes=SCOPES
            )
            logger.info("Google 認証: サービスアカウントを使用")
            return creds
        except Exception as e:
            raise RuntimeError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON のデコードに失敗しました: {e}"
            ) from e

    # 2. OAuth2 フロー（ローカル）
    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json が見つかりません: {CREDENTIALS_FILE}\n"
                    "Google Cloud Console から OAuth2 クライアント認証情報をダウンロードして "
                    "python/ フォルダに配置してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                str(CREDENTIALS_FILE), SCOPES
            )
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json())

    logger.info("Google 認証: OAuth2 トークンを使用")
    return creds


# ────────────────────────────────────────────────────────────────────────────
# 同期処理
# ────────────────────────────────────────────────────────────────────────────

def sync_database(
    database_id: str,
    notion: NotionClient,
    gdocs: GoogleDocsClient,
) -> None:
    """Notion データベースの全ページを Google Drive に同期する。"""
    logger.info(f"データベース同期開始: {database_id}")

    pages = notion.query_database(database_id)
    logger.info(f"  取得ページ数: {len(pages)}")

    success = 0
    errors = 0
    for page in pages:
        title = notion.extract_title(page)
        try:
            blocks = notion.get_page_blocks(page["id"])
            content = notion.blocks_to_text(blocks)
            gdocs.upsert_doc(title, content)
            logger.info(f"  完了: {title}")
            success += 1
        except Exception as e:
            logger.error(f"  エラー [{title}]: {e}")
            errors += 1

    logger.info(f"データベース同期完了: {database_id} (成功={success}, エラー={errors})")


def main() -> None:
    try:
        config = load_config()
    except EnvironmentError as e:
        logger.error(str(e))
        sys.exit(1)

    try:
        creds = get_google_credentials()
    except Exception as e:
        logger.error(f"Google 認証エラー: {e}")
        sys.exit(1)

    notion = NotionClient(config["notion_api_key"])
    gdocs = GoogleDocsClient(creds, config["drive_folder_id"])

    total_errors = 0
    for db_id in config["database_ids"]:
        try:
            sync_database(db_id, notion, gdocs)
        except Exception as e:
            logger.error(f"データベース処理エラー [{db_id}]: {e}")
            total_errors += 1

    if total_errors > 0:
        logger.warning(f"処理中にエラーが発生したデータベース数: {total_errors}")
        sys.exit(1)

    logger.info("=== 全データベースの同期が完了しました ===")


if __name__ == "__main__":
    main()
