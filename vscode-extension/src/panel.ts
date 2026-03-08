import * as vscode from "vscode";

function escapeHtml(text: string): string {
  return text
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

export class ContextCraftPanel {
  public static currentPanel: ContextCraftPanel | undefined;
  private readonly _panel: vscode.WebviewPanel;
  private readonly _extensionUri: vscode.Uri;
  private _disposables: vscode.Disposable[] = [];

  private constructor(panel: vscode.WebviewPanel, extensionUri: vscode.Uri) {
    this._panel = panel;
    this._extensionUri = extensionUri;
    this._panel.onDidDispose(() => this.dispose(), null, this._disposables);
  }

  public static createOrShow(extensionUri: vscode.Uri): ContextCraftPanel {
    const column = vscode.window.activeTextEditor?.viewColumn ?? vscode.ViewColumn.One;
    if (ContextCraftPanel.currentPanel) {
      ContextCraftPanel.currentPanel._panel.reveal(column);
      return ContextCraftPanel.currentPanel;
    }
    const panel = vscode.window.createWebviewPanel(
      "contextcraftOutput",
      "ContextCraft",
      column,
      { enableScripts: false, retainContextWhenHidden: true }
    );
    ContextCraftPanel.currentPanel = new ContextCraftPanel(panel, extensionUri);
    return ContextCraftPanel.currentPanel;
  }

  public show(title: string, content: string): void {
    this._panel.title = title;
    const body = escapeHtml(content);
    this._panel.webview.html = this._getHtml(title, `<pre class="content">${body}</pre>`);
  }

  public showRunning(title: string): void {
    this._panel.title = title;
    this._panel.webview.html = this._getHtml(
      title,
      '<div class="running"><span class="spinner"></span> Running…</div>'
    );
  }

  public showError(title: string, error: string): void {
    this._panel.title = title;
    const body = escapeHtml(error);
    this._panel.webview.html = this._getHtml(
      title,
      `<pre class="content error">${body}</pre>`
    );
  }

  public dispose(): void {
    ContextCraftPanel.currentPanel = undefined;
    this._panel.dispose();
    this._disposables.forEach((d) => d.dispose());
    this._disposables = [];
  }

  private _getHtml(title: string, bodyContent: string): string {
    return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${escapeHtml(title)}</title>
  <style>
    :root {
      --bg: var(--vscode-editor-background);
      --fg: var(--vscode-editor-foreground);
      --header-bg: var(--vscode-editor-inactiveSelectionBackground);
      --font: var(--vscode-editor-font-family, ui-monospace, monospace);
      --error: var(--vscode-editorError-foreground);
    }
    body { margin: 0; padding: 0; background: var(--bg); color: var(--fg); font-family: var(--font); font-size: 13px; }
    .header { padding: 8px 12px; background: var(--header-bg); border-bottom: 1px solid var(--vscode-panel-border); }
    .content { margin: 12px; white-space: pre-wrap; word-break: break-all; overflow-x: auto; }
    .content.error { color: var(--error); }
    .running { margin: 12px; display: flex; align-items: center; gap: 8px; }
    .spinner { width: 18px; height: 18px; border: 2px solid var(--vscode-panel-border); border-top-color: var(--fg); border-radius: 50%; animation: spin 0.8s linear infinite; }
    @keyframes spin { to { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="header">${escapeHtml(title)}</div>
  <div class="scroll">${bodyContent}</div>
</body>
</html>`;
  }
}
