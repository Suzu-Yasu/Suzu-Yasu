"""
Google Drive / Docs API クライアント

指定した Google Drive フォルダに Google Docs を作成・更新します。
ドキュメントはタイトルで識別され、同名の Doc が存在する場合は内容を上書きします。
"""

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from google.oauth2 import credentials as google_credentials


class GoogleDocsClient:
    """Google Drive / Docs API ラッパー"""

    def __init__(self, creds: google_credentials.Credentials, folder_id: str):
        self._folder_id = folder_id
        self._drive = build("drive", "v3", credentials=creds)
        self._docs = build("docs", "v1", credentials=creds)

    # ────────────────────────────────────────────────
    # 公開メソッド
    # ────────────────────────────────────────────────

    def upsert_doc(self, title: str, content: str) -> str:
        """タイトルで Doc を検索し、あれば更新・なければ作成する。Doc ID を返す。"""
        doc_id = self.find_doc_by_title(title)
        if doc_id:
            self.update_doc_content(doc_id, content)
            return doc_id
        else:
            doc_id = self.create_doc(title)
            self.update_doc_content(doc_id, content)
            return doc_id

    def find_doc_by_title(self, title: str) -> str | None:
        """フォルダ内から同名の Google Doc を検索。見つかれば file ID を返す。"""
        safe_title = title.replace("'", "\\'")
        query = (
            f"name = '{safe_title}'"
            f" and '{self._folder_id}' in parents"
            f" and mimeType = 'application/vnd.google-apps.document'"
            f" and trashed = false"
        )
        try:
            result = (
                self._drive.files()
                .list(q=query, fields="files(id, name)", pageSize=1)
                .execute()
            )
            files = result.get("files", [])
            return files[0]["id"] if files else None
        except HttpError as e:
            raise RuntimeError(f"Drive ファイル検索エラー: {e}") from e

    def create_doc(self, title: str) -> str:
        """指定フォルダ内に新しい Google Doc を作成し、file ID を返す。"""
        body = {
            "name": title,
            "mimeType": "application/vnd.google-apps.document",
            "parents": [self._folder_id],
        }
        try:
            file = self._drive.files().create(body=body, fields="id").execute()
            return file["id"]
        except HttpError as e:
            raise RuntimeError(f"Doc 作成エラー [title={title}]: {e}") from e

    def update_doc_content(self, doc_id: str, content: str) -> None:
        """Doc の内容を content で全置換する。"""
        try:
            doc = self._docs.documents().get(documentId=doc_id).execute()
            body_content = doc.get("body", {}).get("content", [])
            end_index = body_content[-1].get("endIndex", 1) if body_content else 1

            requests_body: list[dict] = []

            # 既存コンテンツを削除（末尾の改行は残す）
            if end_index > 1:
                requests_body.append(
                    {
                        "deleteContentRange": {
                            "range": {"startIndex": 1, "endIndex": end_index - 1}
                        }
                    }
                )

            # 新しいコンテンツを挿入
            if content:
                requests_body.append(
                    {"insertText": {"location": {"index": 1}, "text": content}}
                )

            if requests_body:
                self._docs.documents().batchUpdate(
                    documentId=doc_id, body={"requests": requests_body}
                ).execute()

        except HttpError as e:
            raise RuntimeError(f"Doc 更新エラー [doc_id={doc_id}]: {e}") from e
