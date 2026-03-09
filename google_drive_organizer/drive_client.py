"""
drive_client.py
Google Drive API の薄いラッパー。フォルダ検索・作成・ファイル移動を担当。
"""

import os
import logging
from functools import lru_cache
from typing import Optional

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Drive API は drive スコープのみで OK (ファイル移動に必要)
SCOPES = ["https://www.googleapis.com/auth/drive"]

# 認証ファイルのデフォルトパス
DEFAULT_CREDENTIALS_FILE = os.path.join(
    os.path.dirname(__file__), "credentials", "credentials.json"
)
DEFAULT_TOKEN_FILE = os.path.join(
    os.path.dirname(__file__), "credentials", "token.json"
)


# ------------------------------------------------------------------ #
#  認証
# ------------------------------------------------------------------ #

def get_drive_service(
    credentials_file: str = DEFAULT_CREDENTIALS_FILE,
    token_file: str = DEFAULT_TOKEN_FILE,
):
    """OAuth2 認証を行い、Drive API サービスオブジェクトを返す。"""
    creds: Optional[Credentials] = None

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
            logger.info("トークンを更新しました。")
        else:
            if not os.path.exists(credentials_file):
                raise FileNotFoundError(
                    f"credentials.json が見つかりません: {credentials_file}\n"
                    "Google Cloud Console からダウンロードして "
                    "credentials/ フォルダに配置してください。"
                )
            flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            logger.info("新しいトークンを取得しました。")

        os.makedirs(os.path.dirname(token_file), exist_ok=True)
        with open(token_file, "w") as f:
            f.write(creds.to_json())

    return build("drive", "v3", credentials=creds)


# ------------------------------------------------------------------ #
#  DriveClient クラス
# ------------------------------------------------------------------ #

class DriveClient:
    """Google Drive の操作をまとめたクラス。"""

    def __init__(self, service=None, credentials_file: str = DEFAULT_CREDENTIALS_FILE,
                 token_file: str = DEFAULT_TOKEN_FILE):
        self.service = service or get_drive_service(credentials_file, token_file)
        # フォルダ名 → ID のキャッシュ (parent_id, name) → folder_id
        self._folder_cache: dict[tuple[str, str], str] = {}

    # -------------------------------------------------------------- #
    #  フォルダ操作
    # -------------------------------------------------------------- #

    def get_root_id(self) -> str:
        """My Drive のルートフォルダ ID を返す。"""
        result = self.service.files().get(fileId="root", fields="id").execute()
        return result["id"]

    def find_folder(self, name: str, parent_id: str) -> Optional[str]:
        """
        指定した親フォルダ内で name のフォルダを探し、ID を返す。
        見つからなければ None。
        """
        cache_key = (parent_id, name)
        if cache_key in self._folder_cache:
            return self._folder_cache[cache_key]

        query = (
            f"name = '{_escape(name)}' "
            f"and '{parent_id}' in parents "
            f"and mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false"
        )
        try:
            resp = (
                self.service.files()
                .list(q=query, fields="files(id, name)", pageSize=10)
                .execute()
            )
        except HttpError as e:
            logger.error("フォルダ検索エラー: %s", e)
            raise

        files = resp.get("files", [])
        if files:
            folder_id = files[0]["id"]
            self._folder_cache[cache_key] = folder_id
            return folder_id
        return None

    def create_folder(self, name: str, parent_id: str) -> str:
        """指定した親フォルダ内に name のフォルダを作成し、ID を返す。"""
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
            "parents": [parent_id],
        }
        try:
            folder = (
                self.service.files()
                .create(body=metadata, fields="id")
                .execute()
            )
        except HttpError as e:
            logger.error("フォルダ作成エラー: %s", e)
            raise

        folder_id = folder["id"]
        self._folder_cache[(parent_id, name)] = folder_id
        logger.info("フォルダ作成: '%s' (id=%s)", name, folder_id)
        return folder_id

    def get_or_create_folder(self, name: str, parent_id: str) -> str:
        """フォルダが存在すれば ID を返し、なければ作成して返す。"""
        folder_id = self.find_folder(name, parent_id)
        if folder_id:
            return folder_id
        return self.create_folder(name, parent_id)

    def resolve_path(self, path: list[str], root_id: Optional[str] = None) -> str:
        """
        フォルダ名のリストを辿り、末端フォルダの ID を返す。
        途中のフォルダが存在しなければ作成する。
        """
        current_id = root_id or self.get_root_id()
        for folder_name in path:
            current_id = self.get_or_create_folder(folder_name, current_id)
        return current_id

    # -------------------------------------------------------------- #
    #  ファイル操作
    # -------------------------------------------------------------- #

    def list_files_in_folder(self, folder_id: str) -> list[dict]:
        """フォルダ内のファイル一覧を返す (フォルダ除く)。"""
        query = (
            f"'{folder_id}' in parents "
            f"and mimeType != 'application/vnd.google-apps.folder' "
            f"and trashed = false"
        )
        files: list[dict] = []
        page_token = None

        while True:
            try:
                resp = (
                    self.service.files()
                    .list(
                        q=query,
                        fields="nextPageToken, files(id, name, mimeType, parents)",
                        pageSize=100,
                        pageToken=page_token,
                    )
                    .execute()
                )
            except HttpError as e:
                logger.error("ファイル一覧取得エラー: %s", e)
                raise

            files.extend(resp.get("files", []))
            page_token = resp.get("nextPageToken")
            if not page_token:
                break

        return files

    def move_file(self, file_id: str, new_parent_id: str,
                  current_parent_id: Optional[str] = None) -> None:
        """
        ファイルを new_parent_id フォルダに移動する。
        current_parent_id が None の場合は API から取得する。
        """
        if current_parent_id is None:
            meta = (
                self.service.files()
                .get(fileId=file_id, fields="parents")
                .execute()
            )
            current_parent_id = ",".join(meta.get("parents", []))

        try:
            self.service.files().update(
                fileId=file_id,
                addParents=new_parent_id,
                removeParents=current_parent_id,
                fields="id, parents",
            ).execute()
        except HttpError as e:
            logger.error("ファイル移動エラー (id=%s): %s", file_id, e)
            raise

    def find_folder_by_name_in_drive(self, name: str) -> Optional[str]:
        """
        Drive 全体から name のフォルダを検索し、最初に見つかった ID を返す。
        My Drive のトップレベルに近いものを探すのに便利。
        """
        query = (
            f"name = '{_escape(name)}' "
            f"and mimeType = 'application/vnd.google-apps.folder' "
            f"and trashed = false"
        )
        resp = (
            self.service.files()
            .list(q=query, fields="files(id, name)", pageSize=5)
            .execute()
        )
        files = resp.get("files", [])
        return files[0]["id"] if files else None


# ------------------------------------------------------------------ #
#  ユーティリティ
# ------------------------------------------------------------------ #

def _escape(s: str) -> str:
    """Drive API のクエリ文字列用エスケープ。"""
    return s.replace("\\", "\\\\").replace("'", "\\'")
