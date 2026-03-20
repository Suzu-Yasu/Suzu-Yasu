# Notion × NotebookLM 連携ツール

Notion のデータベースを Google Drive の Google Docs として自動同期し、NotebookLM の AI 分析に活用するためのツールです。

```
Notion DB  →  GAS / Python  →  Google Drive (Google Docs)  →  NotebookLM
```

NotebookLM には Notion との公式連携機能がないため、Google Drive を中継点として利用します。

---

## 機能

- Notion データベースの全ページを Google Docs に変換
- 同名の Doc が存在する場合は内容を上書き更新（upsert）
- 複数データベースを一括同期
- **GAS 版**: Google のインフラ上で動作、スケジュール実行に対応
- **Python 版**: ローカル実行または GitHub Actions による自動化に対応

---

## アーキテクチャ

```
┌─────────────────────┐
│     Notion DB       │  ← ページとブロックを Notion API で取得
└────────┬────────────┘
         │ Notion API (REST)
         ▼
┌─────────────────────┐
│  GAS または Python  │  ← ブロックをテキストに変換・Drive に書き込み
└────────┬────────────┘
         │ Google Drive / Docs API
         ▼
┌─────────────────────┐
│ Google Drive フォルダ│  ← Google Docs として保存
└────────┬────────────┘
         │ ソースとして手動追加
         ▼
┌─────────────────────┐
│     NotebookLM      │  ← Notion の内容で AI に質問できる
└─────────────────────┘
```

---

## 前提条件

- Notion アカウント（インテグレーション作成権限）
- Google アカウント（Google Drive、Google Docs へのアクセス）
- Python 3.11 以上（Python 版を使用する場合）

---

## セットアップ

### 1. Notion 側の準備

1. [Notion インテグレーション管理ページ](https://www.notion.so/my-integrations) を開く
2. **「新しいインテグレーション」** を作成する
   - 名前: 任意（例: `NotebookLM Sync`）
   - 権限: **「コンテンツを読み取る」** にチェック
3. 表示される **シークレットキー**（`secret_...`）をメモする → `NOTION_API_KEY`
4. 同期対象の各データベースページを開き、右上の **「...」メニュー → 「接続」** から作成したインテグレーションを追加する
5. データベースの URL からデータベース ID を取得する
   ```
   https://www.notion.so/xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx?v=...
                         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                         この32文字がデータベース ID
   ```

### 2. Google Drive フォルダの準備

1. Google Drive で **新しいフォルダ** を作成する（例: `NotebookLM Sources`）
2. フォルダを開いた URL の末尾をメモする → `GOOGLE_DRIVE_FOLDER_ID`
   ```
   https://drive.google.com/drive/folders/zzzzzzzzzzzzzzzzzzzzzzzzzzzzzzzz
                                          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          この部分がフォルダ ID
   ```

---

## GAS 版のセットアップ

Google Apps Script を使う方法です。ローカル環境の構築不要で、Google のインフラ上で動作します。

### 手順

1. [Google Apps Script](https://script.google.com) を開き、**「新しいプロジェクト」** を作成する
2. エディタ内のデフォルトコードを削除し、[`gas/Code.gs`](gas/Code.gs) の内容を貼り付ける
3. 左メニューの **「プロジェクトの設定」（歯車アイコン）** を開く
4. **「スクリプトプロパティ」** に以下を追加する:

   | プロパティ名 | 値 |
   |---|---|
   | `NOTION_API_KEY` | Notion のシークレットキー |
   | `NOTION_DATABASE_IDS` | データベース ID（複数の場合はカンマ区切り） |
   | `GOOGLE_DRIVE_FOLDER_ID` | Google Drive フォルダ ID |

5. 関数選択プルダウンで **`setupTrigger`** を選択して実行する（毎日 01:00 のトリガーが設定される）
6. 関数選択プルダウンで **`testRun`** を選択して実行し、ログにページ情報が表示されることを確認する
7. 関数選択プルダウンで **`syncAll`** を選択して実行し、Drive に Google Docs が作成されることを確認する

> **注意**: 初回実行時は Google アカウントへのアクセス許可を求められます。「許可」を選択してください。

---

## Python 版のセットアップ

### ローカル実行

1. リポジトリをクローンする:
   ```bash
   git clone <リポジトリURL>
   cd Suzu-Yasu/python
   ```

2. 依存パッケージをインストールする:
   ```bash
   pip install -r requirements.txt
   ```

3. 環境変数ファイルを作成する:
   ```bash
   cp .env.example .env
   # .env をエディタで開いて各値を設定する
   ```

4. Google Cloud で OAuth2 認証情報を準備する:
   1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
   2. 「API とサービス」→「有効な API とサービス」→ **Google Drive API** と **Google Docs API** を有効化
   3. 「認証情報」→「認証情報を作成」→「OAuth 2.0 クライアント ID」→ **デスクトップアプリ** を選択
   4. JSON ファイルをダウンロードし、`python/credentials.json` として配置する

5. スクリプトを実行する（初回はブラウザで認証フローが開く）:
   ```bash
   python main.py
   ```

   認証後は `token.json` が生成され、次回以降はブラウザ認証なしで実行できます。

### GitHub Actions による自動実行

GitHub Actions を使って毎日自動で同期できます。

1. Google Cloud でサービスアカウントを作成する:
   1. 「IAM と管理」→「サービスアカウント」→「サービスアカウントを作成」
   2. ロールは「編集者」または Drive/Docs API の権限を付与
   3. 「鍵」タブ → 「鍵を追加」→「JSON」でキーをダウンロード

2. 同期対象の Google Drive フォルダをサービスアカウントのメールアドレスと共有する（編集者権限）:
   - サービスアカウントのメールアドレス例: `sync-bot@my-project.iam.gserviceaccount.com`

3. サービスアカウント JSON を base64 エンコードする:
   ```bash
   base64 -w0 service-account-key.json
   ```

4. GitHub リポジトリの **Settings → Secrets and variables → Actions** に以下を追加する:

   | シークレット名 | 値 |
   |---|---|
   | `NOTION_API_KEY` | Notion のシークレットキー |
   | `NOTION_DATABASE_IDS` | データベース ID（カンマ区切り） |
   | `GOOGLE_DRIVE_FOLDER_ID` | Google Drive フォルダ ID |
   | `GOOGLE_SERVICE_ACCOUNT_JSON` | base64 エンコードしたサービスアカウント JSON |

5. Actions タブで **「Sync Notion to Google Drive」** ワークフローの **「Run workflow」** をクリックして動作確認する

> ワークフローファイル: [`.github/workflows/sync.yml`](.github/workflows/sync.yml)
> デフォルトのスケジュール: 毎日 00:00 JST（15:00 UTC）

---

## NotebookLM との接続

1. [NotebookLM](https://notebooklm.google.com) を開く
2. ノートブックを作成または開く
3. **「ソース」パネル → 「ソースを追加」→「Google ドライブ」** を選択する
4. 同期先フォルダを選択する
5. NotebookLM が Google Docs を読み込み、Notion の内容を元に質問・要約ができるようになる

> **ヒント**: NotebookLM は API を持たないため、ソースの追加は手動で行う必要があります。
> 同期スクリプトを実行後、NotebookLM で「ソースを更新」するだけで最新の Notion 内容が反映されます。

---

## ファイル構成

```
.
├── gas/
│   └── Code.gs               # Google Apps Script 版
├── python/
│   ├── main.py               # エントリポイント
│   ├── notion_client.py      # Notion API クライアント
│   ├── gdocs_client.py       # Google Drive/Docs API クライアント
│   ├── requirements.txt      # Python 依存パッケージ
│   └── .env.example          # 環境変数テンプレート
└── .github/
    └── workflows/
        └── sync.yml          # GitHub Actions ワークフロー
```

---

## 対応ブロックタイプ

| Notion ブロック | 変換後 |
|---|---|
| 見出し 1 | `# テキスト` |
| 見出し 2 | `## テキスト` |
| 見出し 3 | `### テキスト` |
| 段落 | `テキスト` |
| 箇条書きリスト | `- テキスト` |
| 番号付きリスト | `1. テキスト` |
| ToDoリスト | `[x] テキスト` / `[ ] テキスト` |
| コードブロック | ` ``` テキスト ``` ` |
| 引用 | `> テキスト` |
| コールアウト | `[絵文字] テキスト` |
| 区切り線 | `---` |

---

## 既知の制限

- **ページ名の変更**: Notion でページ名を変更した場合、旧 Doc は Drive に残ります（手動削除が必要）
- **ネストしたブロック**: 子ブロック（インデントされたコンテンツ）は現バージョンでは取得されません
- **GAS の実行時間制限**: ページ数が多い場合、GAS の 6 分制限に達する場合があります
- **NotebookLM の API**: NotebookLM は現在 API を提供していないため、ソース接続は手動操作が必要です

---

## トラブルシューティング

**「Notion API エラー [401]」が出る**
→ `NOTION_API_KEY` が正しいか確認してください。また、対象データベースにインテグレーションが接続されているか確認してください。

**「Notion API エラー [404]」が出る**
→ `NOTION_DATABASE_IDS` のデータベース ID が正しいか確認してください。

**「Drive ファイル検索エラー」が出る**
→ `GOOGLE_DRIVE_FOLDER_ID` が正しいか、Google アカウントのフォルダへのアクセス権があるか確認してください。

**GAS でページが作成されない**
→ `testRun()` を実行してログを確認してください。スクリプトプロパティの設定ミスが多いです。

**GitHub Actions でエラーになる**
→ シークレットが正しく設定されているか確認してください。`GOOGLE_SERVICE_ACCOUNT_JSON` は base64 エンコードされた値を設定する必要があります。
