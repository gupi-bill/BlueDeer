"""python -m bluedeer 入口。"""

import logging

from bluedeer.agent import BlueDeerAgent
from bluedeer.config import load_config


def main():
    config = load_config()
    logging.basicConfig(
        level=getattr(logging, config.get("log_level", "INFO"), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    agent = BlueDeerAgent(config)
    print("BlueDeer Agent 已启动（Mock 模式）。输入 /exit 或 /quit 退出。")

    while True:
        try:
            text = input("你> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n再见。")
            break

        if not text:
            continue
        if text in ("/exit", "/quit", "exit", "quit"):
            print("再见。")
            break

        print(f"BlueDeer> {agent.run(text)}")


if __name__ == "__main__":
    main()
