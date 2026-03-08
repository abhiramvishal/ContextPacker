"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.activate = activate;
exports.deactivate = deactivate;
const vscode = require("vscode");
const config_1 = require("./config");
const panel_1 = require("./panel");
const runner_1 = require("./runner");
function activate(context) {
    context.subscriptions.push(vscode.commands.registerCommand("contextcraft.init", () => runInit(context)), vscode.commands.registerCommand("contextcraft.update", () => runUpdate(context)), vscode.commands.registerCommand("contextcraft.diff", () => runDiff(context)));
}
function deactivate() { }
function getWorkspacePath() {
    const folder = vscode.workspace.workspaceFolders?.[0];
    return folder ? folder.uri.fsPath : null;
}
async function ensureCLI(panel, pythonPath) {
    try {
        const ok = await (0, runner_1.checkCLIInstalled)(pythonPath);
        if (ok)
            return true;
    }
    catch {
        // spawn error (e.g. python not found)
    }
    panel.showError("ContextCraft CLI not found", "ContextCraft CLI not found. Install it with:\n\n  pip install contextcraft");
    const copy = await vscode.window.showErrorMessage("ContextCraft CLI not found. Install it with: pip install contextcraft", "Copy install command");
    if (copy === "Copy install command") {
        await vscode.env.clipboard.writeText("pip install contextcraft");
    }
    return false;
}
async function runInit(context) {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) {
        vscode.window.showErrorMessage("Open a workspace folder first.");
        return;
    }
    const panel = panel_1.ContextCraftPanel.createOrShow(context.extensionUri);
    const config = (0, config_1.getConfig)();
    const pythonPath = config.pythonPath || (await resolvePythonForPanel(panel));
    if (!pythonPath)
        return;
    if (!(await ensureCLI(panel, pythonPath)))
        return;
    const args = [
        "init",
        workspacePath,
        "--model", config.model,
        "--max-tokens", String(config.maxTokens),
    ];
    const env = { ...process.env };
    if (config.apiKey.length > 0) {
        env.ANTHROPIC_API_KEY = config.apiKey;
    }
    panel.showRunning("Generating Context Pack...");
    try {
        const result = await (0, runner_1.runContextCraft)(args, env, config.pythonPath, workspacePath);
        if (result.code === 0) {
            panel.show("Context Pack Ready", result.stdout || "(no output)");
            vscode.window.showInformationMessage("context.pack.md written to workspace root.");
        }
        else {
            panel.showError("ContextCraft init failed", result.stderr || result.stdout || `Exit code ${result.code}`);
        }
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        panel.showError("ContextCraft init failed", msg);
    }
}
async function runUpdate(context) {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) {
        vscode.window.showErrorMessage("Open a workspace folder first.");
        return;
    }
    const panel = panel_1.ContextCraftPanel.createOrShow(context.extensionUri);
    const config = (0, config_1.getConfig)();
    const pythonPath = config.pythonPath || (await resolvePythonForPanel(panel));
    if (!pythonPath)
        return;
    if (!(await ensureCLI(panel, pythonPath)))
        return;
    const args = [
        "update",
        workspacePath,
        "--model", config.model,
        "--max-tokens", String(config.maxTokens),
    ];
    const env = { ...process.env };
    if (config.apiKey.length > 0) {
        env.ANTHROPIC_API_KEY = config.apiKey;
    }
    panel.showRunning("Updating Context Pack...");
    try {
        const result = await (0, runner_1.runContextCraft)(args, env, config.pythonPath, workspacePath);
        if (result.code === 0) {
            panel.show("Context Pack Updated", result.stdout || "(no output)");
            vscode.window.showInformationMessage("Context Pack updated.");
        }
        else {
            panel.showError("ContextCraft update failed", result.stderr || result.stdout || `Exit code ${result.code}`);
        }
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        panel.showError("ContextCraft update failed", msg);
    }
}
async function runDiff(context) {
    const workspacePath = getWorkspacePath();
    if (!workspacePath) {
        vscode.window.showErrorMessage("Open a workspace folder first.");
        return;
    }
    const panel = panel_1.ContextCraftPanel.createOrShow(context.extensionUri);
    const config = (0, config_1.getConfig)();
    const pythonPath = config.pythonPath || (await resolvePythonForPanel(panel));
    if (!pythonPath)
        return;
    if (!(await ensureCLI(panel, pythonPath)))
        return;
    const args = ["diff", workspacePath];
    const env = { ...process.env };
    panel.showRunning("Running diff...");
    try {
        const result = await (0, runner_1.runContextCraft)(args, env, config.pythonPath, workspacePath);
        if (result.code === 0) {
            panel.show("Context Pack Diff", result.stdout || "(no changes)");
        }
        else {
            panel.showError("ContextCraft diff failed", result.stderr || result.stdout || `Exit code ${result.code}`);
        }
    }
    catch (err) {
        const msg = err instanceof Error ? err.message : String(err);
        panel.showError("ContextCraft diff failed", msg);
    }
}
/** Resolve python path when config.pythonPath is empty: try python3 then python. */
async function resolvePythonForPanel(panel) {
    if (await (0, runner_1.checkCLIInstalled)("python3"))
        return "python3";
    if (await (0, runner_1.checkCLIInstalled)("python"))
        return "python";
    return process.platform === "win32" ? "python" : "python3";
}
//# sourceMappingURL=extension.js.map