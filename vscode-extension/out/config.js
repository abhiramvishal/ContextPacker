"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.getConfig = getConfig;
const vscode = require("vscode");
function getConfig() {
    const cfg = vscode.workspace.getConfiguration("contextcraft");
    return {
        apiKey: cfg.get("apiKey", "").trim(),
        model: cfg.get("model", "claude-sonnet-4-5").trim(),
        maxTokens: Math.min(8192, Math.max(100, cfg.get("maxTokens", 2000))),
        pythonPath: cfg.get("pythonPath", "").trim(),
    };
}
//# sourceMappingURL=config.js.map