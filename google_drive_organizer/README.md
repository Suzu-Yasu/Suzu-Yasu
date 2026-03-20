# Google Drive 自動整理スクリプト

`00_Inbox` フォルダに入ってきたファイルを、命名規則のタグ・カテゴリに基づいて
自動で各フォルダに振り分けます。

---

## セットアップ

### 1. 依存パッケージのインストール

```bash
pip install -r requirements.txt
```

### 2. Google Cloud Console での設定

1. [Google Cloud Console](https://console.cloud.google.com/) でプロジェクトを作成
2. **Google Drive API** を有効化
3. **OAuth 2.0 クライアント ID** を作成 (アプリケーションの種類: デスクトップ)
4. ダウンロードした JSON ファイルを `credentials/credentials.json` として保存

```
google_drive_organizer/
└── credentials/
    └── credentials.json   ← ここに配置
```

> `credentials/` フォルダは `.gitignore` に追加済みです。絶対にコミットしないこと。

### 3. 初回認証

スクリプトを初めて実行するとブラウザが開き、Google アカウントの認証を求められます。
認証後、`credentials/token.json` が自動生成され、次回以降は不要になります。

---

## 使い方

```bash
# ドライラン (実際には移動しない・確認のみ)
python organizer.py --dry-run

# 実際に移動
python organizer.py

# 詳細ログ付き
python organizer.py --verbose

# credentials のパスを指定する場合
python organizer.py --credentials /path/to/credentials.json
```

---

## 分類ロジック

ファイル名の命名規則 `YYYYMMDD_【TAG】_Category_Detail_Type.ext` を解析し、
以下のルールで振り分けます。

| タグ | 移動先 |
|------|--------|
| `【LCT】` | `01_University_Lecture/YYYY_Season/科目/` |
| `【STY】` `【RES】` | `02_Self_Study/サブフォルダ/` |
| `【ADM】` `【PRJ】` | `03_Admin_Life/サブフォルダ/` |
| `【MUS】` | `04_Music_Score/Solo or Orchestra or Chamber/` |
| `【PSN】` | `05_Personal_Health/サブフォルダ/` |

### 講義 (`【LCT】`) の詳細ルール

- ファイル名に `exam` / `pastexam` が含まれる → `00_Past_Exams_Archive`
- 日付の月が 1〜7 月 → `YYYY_Spring`、8〜12 月 → `YYYY_Autumn`
- Category が `LinAlg` / `Calc` / `CS` 等 → 対応する科目フォルダへ
- ファイル名に `Note` / `Slide` / `Report` 等 → `01_Lecture_Notes` / `02_Handouts` / `03_Assignments`

### 音楽 (`【MUS】`) の詳細ルール

| キーワード | 移動先 |
|-----------|--------|
| `VcConc` `Conc` `Sonat` `Solo` `Suite` | `01_Solo` |
| `Sym` `Orch` `Overture` | `02_Orchestra` |
| `Quartet` `Trio` `Quintet` `Chamber` | `03_Chamber` |
| 判定不能 | `99_Unsorted` |

---

## テスト

```bash
pytest test_classifier.py -v
```

---

## 定期実行 (cron)

毎朝 8 時に自動実行する例 (Mac / Linux):

```bash
# crontab -e で追加
0 8 * * * cd /path/to/google_drive_organizer && python organizer.py >> organizer.log 2>&1
```
