"""
Notion API クライアント

Notion データベースのページとブロックを取得し、
Google Docs に適したプレーンテキストに変換します。
"""

import requests


NOTION_VERSION = "2022-06-28"
NOTION_BASE_URL = "https://api.notion.com/v1"

# ブロックタイプごとのプレフィックス定義
BLOCK_PREFIX = {
    "heading_1": "# ",
    "heading_2": "## ",
    "heading_3": "### ",
    "paragraph": "",
    "bulleted_list_item": "- ",
    "quote": "> ",
}


class NotionClient:
    """Notion API ラッパー"""

    def __init__(self, api_key: str):
        self._headers = {
            "Authorization": f"Bearer {api_key}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    # ────────────────────────────────────────────────
    # 公開メソッド
    # ────────────────────────────────────────────────

    def query_database(self, database_id: str) -> list[dict]:
        """データベースの全ページを取得（ページネーション対応）"""
        pages = []
        cursor = None
        has_more = True

        while has_more:
            body: dict = {"page_size": 100}
            if cursor:
                body["start_cursor"] = cursor

            data = self._post(f"/databases/{database_id}/query", body)
            pages.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            cursor = data.get("next_cursor")

        return pages

    def get_page_blocks(self, page_id: str) -> list[dict]:
        """ページのブロック一覧を取得（ページネーション対応）"""
        blocks = []
        cursor = None
        has_more = True

        while has_more:
            params = {"page_size": 100}
            if cursor:
                params["start_cursor"] = cursor

            data = self._get(f"/blocks/{page_id}/children", params=params)
            blocks.extend(data.get("results", []))
            has_more = data.get("has_more", False)
            cursor = data.get("next_cursor")

        return blocks

    @staticmethod
    def extract_title(page: dict) -> str:
        """ページオブジェクトからタイトルを抽出"""
        for prop in page.get("properties", {}).values():
            if prop.get("type") == "title":
                rich_texts = prop.get("title", [])
                return "".join(t.get("plain_text", "") for t in rich_texts) or "Untitled"
        return "Untitled"

    @staticmethod
    def blocks_to_text(blocks: list[dict]) -> str:
        """ブロック配列をプレーンテキストに変換"""
        lines = []
        numbered_index = 1

        for block in blocks:
            block_type = block.get("type", "")
            content = block.get(block_type, {})
            rich_texts = content.get("rich_text", [])
            text = "".join(t.get("plain_text", "") for t in rich_texts)

            if block_type in BLOCK_PREFIX:
                lines.append(BLOCK_PREFIX[block_type] + text)
                if block_type != "bulleted_list_item":
                    numbered_index = 1

            elif block_type == "numbered_list_item":
                lines.append(f"{numbered_index}. {text}")
                numbered_index += 1

            elif block_type == "to_do":
                checked = "[x]" if content.get("checked") else "[ ]"
                lines.append(f"{checked} {text}")
                numbered_index = 1

            elif block_type == "code":
                lines.append("```")
                lines.append(text)
                lines.append("```")
                numbered_index = 1

            elif block_type == "callout":
                icon = content.get("icon", {})
                emoji = icon.get("emoji", "") if isinstance(icon, dict) else ""
                lines.append(f"[{emoji}] {text}")
                numbered_index = 1

            elif block_type == "divider":
                lines.append("---")
                numbered_index = 1

            else:
                if text:
                    lines.append(text)

        return "\n".join(lines)

    # ────────────────────────────────────────────────
    # 内部メソッド
    # ────────────────────────────────────────────────

    def _post(self, path: str, body: dict) -> dict:
        url = NOTION_BASE_URL + path
        response = requests.post(url, headers=self._headers, json=body, timeout=30)
        self._raise_for_status(response)
        return response.json()

    def _get(self, path: str, params: dict | None = None) -> dict:
        url = NOTION_BASE_URL + path
        response = requests.get(url, headers=self._headers, params=params, timeout=30)
        self._raise_for_status(response)
        return response.json()

    @staticmethod
    def _raise_for_status(response: requests.Response) -> None:
        if not response.ok:
            raise RuntimeError(
                f"Notion API エラー [{response.status_code}]: {response.text}"
            )
