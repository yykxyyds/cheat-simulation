"""
测试 .env 中所有 API Key 是否可用，能否得到模型正常回复。
每个 API 发一条简单消息，检查响应是否正常。
"""
import os
import sys
import json
import time
import requests
from pathlib import Path

# .env 文件路径
ENV_FILE = Path(__file__).resolve().parent.parent / ".env"

# ── 解析 .env 文件 ──
def load_env(path: Path) -> dict:
    env = {}
    if not path.exists():
        print(f"❌ .env 文件不存在: {path}")
        return env
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env[key.strip()] = value.strip()
    return env

# ── API 配置 ──
API_CONFIGS = [
    # NVIDIA NIM
    {
        "name": "NVIDIA NIM (MiniMax M2.7)",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model": "minimaxai/minimax-m2.7",
    },
    {
        "name": "NVIDIA NIM (Qwen 3.5)",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model": "qwen/qwen3.5-397b-a17b",
    },
    {
        "name": "NVIDIA NIM (Mistral Large)",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model": "mistralai/mistral-large-3-675b-instruct-2512",
    },
    # DeepSeek
    {
        "name": "DeepSeek",
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    # GLM / ZhipuAI
    {
        "name": "ZhipuAI GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "api_key_env": "GLM_API_KEY",
        "model": "glm-4-flash",
    },
    # GPT 代理
    {
        "name": "GPT Proxy (gmn.chuangzuoli.com)",
        "base_url": "https://gmn.chuangzuoli.com/v1",
        "api_key_env": "GPT_API_KEY",
        "model": "gpt-4o",
    },
]

TEST_MESSAGE = "你好，请用一句话介绍你自己。"
TIMEOUT = (15, 60)  # (connect, read)


def test_api(config: dict, api_key: str) -> bool:
    """测试单个 API，返回是否成功"""
    name = config["name"]
    base_url = config["base_url"].rstrip("/")
    model = config["model"]
    url = f"{base_url}/chat/completions"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": TEST_MESSAGE}],
        "max_tokens": 200,
        "temperature": 0.0,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    print(f"\n{'='*60}")
    print(f"🔍 测试: {name}")
    print(f"   URL: {url}")
    print(f"   Model: {model}")

    try:
        # 不走代理
        resp = requests.post(
            url,
            json=payload,
            headers=headers,
            timeout=TIMEOUT,
            proxies={"http": None, "https": None},
        )
        print(f"   HTTP Status: {resp.status_code}")

        if resp.status_code != 200:
            print(f"   ❌ 失败: {resp.text[:500]}")
            return False

        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if content.strip():
            # 截取前 200 字符显示
            preview = content[:200].replace("\n", "\\n")
            print(f"   ✅ 成功! 响应: {preview}")
            return True
        else:
            print(f"   ❌ 空响应: {json.dumps(data, ensure_ascii=False)[:500]}")
            return False

    except requests.exceptions.Timeout:
        print(f"   ❌ 超时 (connect={TIMEOUT[0]}s, read={TIMEOUT[1]}s)")
        return False
    except requests.exceptions.ConnectionError as e:
        print(f"   ❌ 连接失败: {e}")
        return False
    except Exception as e:
        print(f"   ❌ 异常: {e}")
        return False


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    env = load_env(ENV_FILE)
    if not env:
        print("无法加载 .env 文件，退出。")
        sys.exit(1)

    # 去除代理环境变量，直连
    for var in ("HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy", "ALL_PROXY", "all_proxy"):
        os.environ.pop(var, None)

    results = {}
    for config in API_CONFIGS:
        key = env.get(config["api_key_env"], "")
        if not key:
            print(f"\n⚠️  跳过 {config['name']}: 未找到 {config['api_key_env']}")
            results[config["name"]] = "SKIPPED (no key)"
            continue

        success = test_api(config, key)
        results[config["name"]] = "✅ PASS" if success else "❌ FAIL"
        time.sleep(0.5)  # 避免请求太密集

    # ── 汇总 ──
    print(f"\n\n{'='*60}")
    print("📊 测试汇总")
    print(f"{'='*60}")
    for name, result in results.items():
        print(f"  {result:10s}  {name}")

    total = len(results)
    passed = sum(1 for v in results.values() if "PASS" in v)
    failed = sum(1 for v in results.values() if "FAIL" in v)
    skipped = sum(1 for v in results.values() if "SKIP" in v)
    print(f"\n总计: {total} | 通过: {passed} | 失败: {failed} | 跳过: {skipped}")


if __name__ == "__main__":
    main()
