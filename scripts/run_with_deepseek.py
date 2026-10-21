"""Load a private DeepSeek key, check the API, or start the local RAG UI."""

import argparse
import os
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ENV_FILE = ROOT / ".env"


def load_local_env(path: Path = ENV_FILE) -> None:
    """Read only the two supported settings; existing environment variables win."""
    if not path.is_file():
        raise RuntimeError(f"找不到 {path}；请复制 .env.example 为 .env，然后填写 DEEPSEEK_API_KEY。")
    for raw_line in path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name = name.strip()
        if name not in ("DEEPSEEK_API_KEY", "DEEPSEEK_MODEL"):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if value and not os.environ.get(name):
            os.environ[name] = value


def require_key() -> None:
    key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not key or key.upper().startswith(("PASTE_", "YOUR_")):
        raise RuntimeError(f"请先在 {ENV_FILE} 的 DEEPSEEK_API_KEY= 后填写真实密钥。")


def check_api() -> None:
    from raglab.generation import generate_answer

    evidence = [{"source_path": "local-check", "heading_path": ["API 测试"],
                 "start_line": 1, "end_line": 1, "text": "测试事实：2 + 2 = 4。"}]
    result = generate_answer("根据给定证据，2 + 2 等于几？", evidence)
    print(f"DeepSeek 调用成功，模型：{result['model']}")
    print(f"回答：{result['answer']}")
    print(f"本次 token 用量：{result['usage'].get('total_tokens', '未返回')}")


def main() -> int:
    parser = argparse.ArgumentParser(description="用本地 .env 调用 DeepSeek 或启动 RAG 页面")
    parser.add_argument("--check", action="store_true", help="发起一次小额 API 调用，验证密钥")
    parser.add_argument("--port", type=int, default=8765, help="页面端口，默认 8765")
    args = parser.parse_args()
    if not 1024 <= args.port <= 65535:
        parser.error("端口必须在 1024 到 65535 之间")
    try:
        load_local_env()
        require_key()
        if args.check:
            check_api()
        else:
            local_model_cache = ROOT / ".venv" / "hf" / "hub"
            if local_model_cache.is_dir() and not os.environ.get("HF_HOME"):
                os.environ["HF_HOME"] = str(local_model_cache.parent)
            print(f"启动页面：http://127.0.0.1:{args.port}/", flush=True)
            return subprocess.call([sys.executable, "-m", "raglab.web", "--port", str(args.port)],
                                   cwd=ROOT)
    except RuntimeError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    raise SystemExit(main())
