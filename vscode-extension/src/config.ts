import * as vscode from "vscode";

export interface ContextCraftConfig {
  apiKey: string;
  model: string;
  maxTokens: number;
  pythonPath: string;
}

export function getConfig(): ContextCraftConfig {
  const cfg = vscode.workspace.getConfiguration("contextcraft");
  return {
    apiKey: cfg.get<string>("apiKey", "").trim(),
    model: cfg.get<string>("model", "claude-sonnet-4-5").trim(),
    maxTokens: Math.min(8192, Math.max(100, cfg.get<number>("maxTokens", 2000))),
    pythonPath: cfg.get<string>("pythonPath", "").trim(),
  };
}
