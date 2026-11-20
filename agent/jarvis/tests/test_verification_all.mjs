import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const runner = fileURLToPath(new URL("./run_browser_qa.py", import.meta.url));
const result = spawnSync("python3", [runner], { stdio: "inherit" });
if (result.error) throw result.error;
process.exitCode = result.status ?? 1;
