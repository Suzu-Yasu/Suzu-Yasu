/**
 * Notion → Google Drive → NotebookLM 連携スクリプト
 *
 * 設定方法：
 *   1. スクリプトエディタ → プロジェクトの設定 → スクリプトプロパティ に以下を追加
 *      NOTION_API_KEY       : Notion インテグレーションのシークレットキー
 *      NOTION_DATABASE_IDS  : 対象データベース ID（複数の場合はカンマ区切り）
 *      GOOGLE_DRIVE_FOLDER_ID: 出力先 Google Drive フォルダ ID
 *   2. setupTrigger() を1回だけ手動実行してトリガーを設定
 *   3. syncAll() を手動実行して動作確認
 */

// ────────────────────────────────────────────────────────────────────────────
// 定数・設定
// ────────────────────────────────────────────────────────────────────────────

var NOTION_VERSION = '2022-06-28';
var NOTION_BASE_URL = 'https://api.notion.com/v1';

/**
 * スクリプトプロパティから設定を読み込む
 * @returns {{ apiKey: string, databaseIds: string[], folderId: string }}
 */
function getConfig() {
  var props = PropertiesService.getScriptProperties();
  var apiKey = props.getProperty('NOTION_API_KEY');
  var dbIds = props.getProperty('NOTION_DATABASE_IDS');
  var folderId = props.getProperty('GOOGLE_DRIVE_FOLDER_ID');

  if (!apiKey || !dbIds || !folderId) {
    throw new Error(
      'スクリプトプロパティが設定されていません。\n' +
      'NOTION_API_KEY, NOTION_DATABASE_IDS, GOOGLE_DRIVE_FOLDER_ID を設定してください。'
    );
  }

  return {
    apiKey: apiKey,
    databaseIds: dbIds.split(',').map(function(id) { return id.trim(); }).filter(Boolean),
    folderId: folderId.trim()
  };
}

// ────────────────────────────────────────────────────────────────────────────
// Notion API
// ────────────────────────────────────────────────────────────────────────────

/**
 * Notion API への共通 POST リクエスト
 */
function notionPost(path, body, apiKey) {
  var options = {
    method: 'post',
    contentType: 'application/json',
    headers: {
      'Authorization': 'Bearer ' + apiKey,
      'Notion-Version': NOTION_VERSION
    },
    payload: JSON.stringify(body),
    muteHttpExceptions: true
  };
  var response = UrlFetchApp.fetch(NOTION_BASE_URL + path, options);
  var code = response.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error('Notion API エラー [' + code + ']: ' + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

/**
 * Notion API への共通 GET リクエスト
 */
function notionGet(path, apiKey) {
  var options = {
    method: 'get',
    headers: {
      'Authorization': 'Bearer ' + apiKey,
      'Notion-Version': NOTION_VERSION
    },
    muteHttpExceptions: true
  };
  var response = UrlFetchApp.fetch(NOTION_BASE_URL + path, options);
  var code = response.getResponseCode();
  if (code < 200 || code >= 300) {
    throw new Error('Notion API エラー [' + code + ']: ' + response.getContentText());
  }
  return JSON.parse(response.getContentText());
}

/**
 * データベースの全ページを取得（ページネーション対応）
 * @returns {Object[]} ページオブジェクトの配列
 */
function fetchAllPages(databaseId, apiKey) {
  var pages = [];
  var cursor = null;
  var hasMore = true;

  while (hasMore) {
    var body = { page_size: 100 };
    if (cursor) body.start_cursor = cursor;

    var result = notionPost('/databases/' + databaseId + '/query', body, apiKey);
    pages = pages.concat(result.results);
    hasMore = result.has_more;
    cursor = result.next_cursor;
  }

  Logger.log('データベース ' + databaseId + ': ' + pages.length + ' ページ取得');
  return pages;
}

/**
 * ページのブロック一覧を取得（ページネーション対応）
 * @returns {Object[]} ブロックオブジェクトの配列
 */
function fetchPageBlocks(pageId, apiKey) {
  var blocks = [];
  var cursor = null;
  var hasMore = true;

  while (hasMore) {
    var path = '/blocks/' + pageId + '/children?page_size=100';
    if (cursor) path += '&start_cursor=' + encodeURIComponent(cursor);

    var result = notionGet(path, apiKey);
    blocks = blocks.concat(result.results);
    hasMore = result.has_more;
    cursor = result.next_cursor;
  }

  return blocks;
}

/**
 * ページオブジェクトからタイトルを抽出
 * @returns {string} タイトル文字列（取得不可の場合は "Untitled"）
 */
function extractTitle(page) {
  var properties = page.properties || {};
  for (var key in properties) {
    var prop = properties[key];
    if (prop.type === 'title' && prop.title && prop.title.length > 0) {
      return prop.title.map(function(t) { return t.plain_text || ''; }).join('');
    }
  }
  return 'Untitled';
}

/**
 * rich_text 配列からプレーンテキストを結合
 */
function richTextToPlain(richTexts) {
  if (!richTexts || richTexts.length === 0) return '';
  return richTexts.map(function(t) { return t.plain_text || ''; }).join('');
}

/**
 * ブロック配列をプレーンテキストに変換
 * @returns {string} 変換済みテキスト
 */
function blocksToText(blocks) {
  var lines = [];
  var numberedIndex = 1;

  blocks.forEach(function(block) {
    var type = block.type;
    var content = block[type];
    if (!content) return;

    var text = richTextToPlain(content.rich_text);

    switch (type) {
      case 'heading_1':
        lines.push('# ' + text);
        numberedIndex = 1;
        break;
      case 'heading_2':
        lines.push('## ' + text);
        numberedIndex = 1;
        break;
      case 'heading_3':
        lines.push('### ' + text);
        numberedIndex = 1;
        break;
      case 'paragraph':
        lines.push(text);
        numberedIndex = 1;
        break;
      case 'bulleted_list_item':
        lines.push('- ' + text);
        break;
      case 'numbered_list_item':
        lines.push(numberedIndex + '. ' + text);
        numberedIndex++;
        break;
      case 'to_do':
        var checked = content.checked ? '[x]' : '[ ]';
        lines.push(checked + ' ' + text);
        numberedIndex = 1;
        break;
      case 'code':
        lines.push('```');
        lines.push(text);
        lines.push('```');
        numberedIndex = 1;
        break;
      case 'quote':
        lines.push('> ' + text);
        numberedIndex = 1;
        break;
      case 'callout':
        var emoji = (content.icon && content.icon.emoji) ? content.icon.emoji : '';
        lines.push('[' + emoji + '] ' + text);
        numberedIndex = 1;
        break;
      case 'divider':
        lines.push('---');
        numberedIndex = 1;
        break;
      default:
        if (text) lines.push(text);
        break;
    }
  });

  return lines.join('\n');
}

// ────────────────────────────────────────────────────────────────────────────
// Google Drive / Docs 操作
// ────────────────────────────────────────────────────────────────────────────

/**
 * 指定フォルダ内からタイトルが一致する Google Doc を検索
 * @returns {GoogleAppsScript.Drive.File|null}
 */
function findDocInFolder(title, folderId) {
  var query = "title = '" + title.replace(/'/g, "\\'") + "'" +
    " and '" + folderId + "' in parents" +
    " and mimeType = 'application/vnd.google-apps.document'" +
    " and trashed = false";
  var files = DriveApp.searchFiles(query);
  if (files.hasNext()) return files.next();
  return null;
}

/**
 * Google Doc のコンテンツを指定テキストで全置換
 */
function updateDocContent(docId, content) {
  var doc = DocumentApp.openById(docId);
  var body = doc.getBody();
  body.clear();
  if (content) {
    body.insertParagraph(0, content);
  }
  doc.saveAndClose();
}

/**
 * Notion ページ → Google Doc を upsert（作成または更新）
 */
function upsertGoogleDoc(page, apiKey, folderId) {
  var title = extractTitle(page);
  var blocks = fetchPageBlocks(page.id, apiKey);
  var content = blocksToText(blocks);

  var existingFile = findDocInFolder(title, folderId);

  if (existingFile) {
    updateDocContent(existingFile.getId(), content);
    Logger.log('更新: ' + title);
  } else {
    var doc = DocumentApp.create(title);
    var docFile = DriveApp.getFileById(doc.getId());
    docFile.moveTo(DriveApp.getFolderById(folderId));
    updateDocContent(doc.getId(), content);
    Logger.log('作成: ' + title);
  }
}

// ────────────────────────────────────────────────────────────────────────────
// メイン処理
// ────────────────────────────────────────────────────────────────────────────

/**
 * 指定データベースを同期
 */
function syncDatabase(databaseId, apiKey, folderId) {
  Logger.log('--- データベース同期開始: ' + databaseId + ' ---');
  var pages = fetchAllPages(databaseId, apiKey);
  pages.forEach(function(page) {
    try {
      upsertGoogleDoc(page, apiKey, folderId);
    } catch (e) {
      Logger.log('ページ処理エラー [' + page.id + ']: ' + e.message);
    }
  });
  Logger.log('--- データベース同期完了: ' + databaseId + ' ---');
}

/**
 * 全データベースを同期（トリガーのエントリポイント）
 */
function syncAll() {
  var config = getConfig();
  config.databaseIds.forEach(function(dbId) {
    try {
      syncDatabase(dbId, config.apiKey, config.folderId);
    } catch (e) {
      Logger.log('データベースエラー [' + dbId + ']: ' + e.message);
    }
  });
  Logger.log('=== 全データベースの同期が完了しました ===');
}

// ────────────────────────────────────────────────────────────────────────────
// ユーティリティ
// ────────────────────────────────────────────────────────────────────────────

/**
 * 日次トリガーを設定（1回だけ手動実行）
 * 実行前に既存の syncAll トリガーは削除されます。
 */
function setupTrigger() {
  // 既存トリガーを削除
  ScriptApp.getProjectTriggers().forEach(function(trigger) {
    if (trigger.getHandlerFunction() === 'syncAll') {
      ScriptApp.deleteTrigger(trigger);
    }
  });

  // 毎日 AM 1:00 に実行
  ScriptApp.newTrigger('syncAll')
    .timeBased()
    .atHour(1)
    .everyDays(1)
    .create();

  Logger.log('日次トリガーを設定しました（毎日 01:00 実行）');
}

/**
 * 動作テスト用（Drive への書き込みは行わない）
 * 設定と Notion API 接続を確認したい場合に実行
 */
function testRun() {
  var config = getConfig();
  Logger.log('設定確認: データベース数 = ' + config.databaseIds.length);

  config.databaseIds.forEach(function(dbId) {
    Logger.log('データベース ID: ' + dbId);
    var pages = fetchAllPages(dbId, config.apiKey);
    Logger.log('ページ数: ' + pages.length);
    if (pages.length > 0) {
      Logger.log('最初のページタイトル: ' + extractTitle(pages[0]));
    }
  });

  Logger.log('テスト完了。Drive への書き込みは行っていません。');
}
