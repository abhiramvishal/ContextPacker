import { spawn } from "child_process";

const CONTEXTCRAFT_MODULE = "contextcraft";

export interface RunResult {
  stdout: string;
  stderr: string;
  code: number;
}

/**
 * Resolve Python executable: use config path if set, else try python3 then python.
 */
async function resolvePythonPath(configPythonPath: string): Promise<string> {
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
export function checkCLIInstalled(pythonPath: string): Promise<boolean> {
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonPath, ["-m", CONTEXTCRAFT_MODULE, "--version"], {
      env: process.env,
      stdio: ["ignore", "pipe", "pipe"],
    });
    proc.on("error", (err: NodeJS.ErrnoException) => {
      if (err.code === "ENOENT") {
        resolve(false);
      } else {
        reject(err);
      }
    });
    proc.on("close", (code) => resolve(code === 0));
    proc.stdout?.on("data", () => {});
    proc.stderr?.on("data", () => {});
  });
}

/**
 * Run contextcraft CLI as subprocess. Uses config.pythonPath if set, else python3 then python.
 * Rejects only on spawn errors.
 */
export async function runContextCraft(
  args: string[],
  env: NodeJS.ProcessEnv,
  configPythonPath: string,
  cwd?: string
): Promise<RunResult> {
  const pythonPath = await resolvePythonPath(configPythonPath);
  return new Promise((resolve, reject) => {
    const proc = spawn(pythonPath, ["-m", CONTEXTCRAFT_MODULE, ...args], {
      env: { ...process.env, ...env },
      cwd: cwd ?? process.cwd(),
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    proc.stdout?.setEncoding("utf8");
    proc.stderr?.setEncoding("utf8");
    proc.stdout?.on("data", (chunk: string) => { stdout += chunk; });
    proc.stderr?.on("data", (chunk: string) => { stderr += chunk; });

    proc.on("error", (err: NodeJS.ErrnoException) => reject(err));
    proc.on("close", (code, signal) => {
      resolve({
        stdout,
        stderr,
        code: code ?? (signal ? 1 : 0),
      });
    });
  });
}
