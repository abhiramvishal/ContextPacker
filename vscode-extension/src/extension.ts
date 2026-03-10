import * as vscode from "vscode";
import { getConfig } from "./config";
import { ContextCraftPanel } from "./panel";
import { checkCLIInstalled, runContextCraft } from "./runner";

export function activate(context: vscode.ExtensionContext): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("contextcraft.init", () => runInit(context)),
    vscode.commands.registerCommand("contextcraft.update", () => runUpdate(context)),
    vscode.commands.registerCommand("contextcraft.diff", () => runDiff(context))
  );
}

export function deactivate(): void {}

function getWorkspacePath(): string | null {
  const folder = vscode.workspace.workspaceFolders?.[0];
  return folder ? folder.uri.fsPath : null;
}

async function ensureCLI(panel: ContextCraftPanel, pythonPath: string): Promise<boolean> {
  try {
    const ok = await checkCLIInstalled(pythonPath);
    if (ok) return true;
  } catch {
    // spawn error (e.g. python not found)
  }
  panel.showError(
    "ContextCraft CLI not found",
    "ContextCraft CLI not found. Install it with:\n\n  pip install llm-codepac"
  );
  const copy = await vscode.window.showErrorMessage(
    "ContextCraft CLI not found. Install it with: pip install llm-codepac",
    "Copy install command"
  );
  if (copy === "Copy install command") {
    await vscode.env.clipboard.writeText("pip install llm-codepac");
  }
  return false;
}

async function runInit(context: vscode.ExtensionContext): Promise<void> {
  const workspacePath = getWorkspacePath();
  if (!workspacePath) {
    vscode.window.showErrorMessage("Open a workspace folder first.");
    return;
  }

  const panel = ContextCraftPanel.createOrShow(context.extensionUri);
  const config = getConfig();

  const pythonPath = config.pythonPath || (await resolvePythonForPanel(panel));
  if (!pythonPath) return;
  if (!(await ensureCLI(panel, pythonPath))) return;

  const args = [
    "init",
    workspacePath,
    "--model", config.model,
    "--max-tokens", String(config.maxTokens),
  ];
  const env: NodeJS.ProcessEnv = { ...process.env };
  if (config.apiKey.length > 0) {
    env.ANTHROPIC_API_KEY = config.apiKey;
  }

  panel.showRunning("Generating Context Pack...");

  try {
    const result = await runContextCraft(args, env, config.pythonPath, workspacePath);
    if (result.code === 0) {
      panel.show("Context Pack Ready", result.stdout || "(no output)");
      vscode.window.showInformationMessage("context.pack.md written to workspace root.");
    } else {
      panel.showError("ContextCraft init failed", result.stderr || result.stdout || `Exit code ${result.code}`);
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    panel.showError("ContextCraft init failed", msg);
  }
}

async function runUpdate(context: vscode.ExtensionContext): Promise<void> {
  const workspacePath = getWorkspacePath();
  if (!workspacePath) {
    vscode.window.showErrorMessage("Open a workspace folder first.");
    return;
  }

  const panel = ContextCraftPanel.createOrShow(context.extensionUri);
  const config = getConfig();

  const pythonPath = config.pythonPath || (await resolvePythonForPanel(panel));
  if (!pythonPath) return;
  if (!(await ensureCLI(panel, pythonPath))) return;

  const args = [
    "update",
    workspacePath,
    "--model", config.model,
    "--max-tokens", String(config.maxTokens),
  ];
  const env: NodeJS.ProcessEnv = { ...process.env };
  if (config.apiKey.length > 0) {
    env.ANTHROPIC_API_KEY = config.apiKey;
  }

  panel.showRunning("Updating Context Pack...");

  try {
    const result = await runContextCraft(args, env, config.pythonPath, workspacePath);
    if (result.code === 0) {
      panel.show("Context Pack Updated", result.stdout || "(no output)");
      vscode.window.showInformationMessage("Context Pack updated.");
    } else {
      panel.showError("ContextCraft update failed", result.stderr || result.stdout || `Exit code ${result.code}`);
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    panel.showError("ContextCraft update failed", msg);
  }
}

async function runDiff(context: vscode.ExtensionContext): Promise<void> {
  const workspacePath = getWorkspacePath();
  if (!workspacePath) {
    vscode.window.showErrorMessage("Open a workspace folder first.");
    return;
  }

  const panel = ContextCraftPanel.createOrShow(context.extensionUri);
  const config = getConfig();

  const pythonPath = config.pythonPath || (await resolvePythonForPanel(panel));
  if (!pythonPath) return;
  if (!(await ensureCLI(panel, pythonPath))) return;

  const args = ["diff", workspacePath];
  const env: NodeJS.ProcessEnv = { ...process.env };

  panel.showRunning("Running diff...");

  try {
    const result = await runContextCraft(args, env, config.pythonPath, workspacePath);
    if (result.code === 0) {
      panel.show("Context Pack Diff", result.stdout || "(no changes)");
    } else {
      panel.showError("ContextCraft diff failed", result.stderr || result.stdout || `Exit code ${result.code}`);
    }
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    panel.showError("ContextCraft diff failed", msg);
  }
}

/** Resolve python path when config.pythonPath is empty: try python3 then python. */
async function resolvePythonForPanel(panel: ContextCraftPanel): Promise<string> {
  if (await checkCLIInstalled("python3")) return "python3";
  if (await checkCLIInstalled("python")) return "python";
  return process.platform === "win32" ? "python" : "python3";
}
