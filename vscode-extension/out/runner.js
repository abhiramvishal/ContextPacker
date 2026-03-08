"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.checkCLIInstalled = checkCLIInstalled;
exports.runContextCraft = runContextCraft;
const child_process_1 = require("child_process");
const CONTEXTCRAFT_MODULE = "contextcraft";
/**
 * Resolve Python executable: use config path if set, else try python3 then python.
 */
async function resolvePythonPath(configPythonPath) {
    if (configPythonPath.length > 0) {
        return configPythonPath;
    }
    if (await checkCLIInstalled("python3")) {
        return "python3";
    }
    if (await checkCLIInstalled("python")) {
        return "python";
    }
    return process.platform === "win32" ? "python" : "python3";
}
/**
 * Run Python with -m contextcraft --version. Returns true if exit code 0.
 * Rejects on spawn errors (e.g. ENOENT).
 */
function checkCLIInstalled(pythonPath) {
    return new Promise((resolve, reject) => {
        const proc = (0, child_process_1.spawn)(pythonPath, ["-m", CONTEXTCRAFT_MODULE, "--version"], {
            env: process.env,
            stdio: ["ignore", "pipe", "pipe"],
        });
        proc.on("error", (err) => {
            if (err.code === "ENOENT") {
                resolve(false);
            }
            else {
                reject(err);
            }
        });
        proc.on("close", (code) => resolve(code === 0));
        proc.stdout?.on("data", () => { });
        proc.stderr?.on("data", () => { });
    });
}
/**
 * Run contextcraft CLI as subprocess. Uses config.pythonPath if set, else python3 then python.
 * Rejects only on spawn errors.
 */
async function runContextCraft(args, env, configPythonPath, cwd) {
    const pythonPath = await resolvePythonPath(configPythonPath);
    return new Promise((resolve, reject) => {
        const proc = (0, child_process_1.spawn)(pythonPath, ["-m", CONTEXTCRAFT_MODULE, ...args], {
            env: { ...process.env, ...env },
            cwd: cwd ?? process.cwd(),
            stdio: ["ignore", "pipe", "pipe"],
        });
        let stdout = "";
        let stderr = "";
        proc.stdout?.setEncoding("utf8");
        proc.stderr?.setEncoding("utf8");
        proc.stdout?.on("data", (chunk) => { stdout += chunk; });
        proc.stderr?.on("data", (chunk) => { stderr += chunk; });
        proc.on("error", (err) => reject(err));
        proc.on("close", (code, signal) => {
            resolve({
                stdout,
                stderr,
                code: code ?? (signal ? 1 : 0),
            });
        });
    });
}
//# sourceMappingURL=runner.js.map