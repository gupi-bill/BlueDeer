#!/usr/bin/env python3
"""BlueDeer 项目一键初始化脚本。

功能：
1. 创建 Python 虚拟环境
2. 安装项目依赖
3. 运行测试套件
4. 验证配置

用法：
    python scripts/init_project.py [--venv-dir .venv] [--skip-tests]
"""

from __future__ import annotations

import argparse
import platform
import subprocess
import sys
from pathlib import Path


def run(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
    """执行命令并打印输出。"""
    print(f"[运行] {' '.join(cmd)}")
    return subprocess.run(cmd, check=False, **kwargs)


def main() -> int:
    parser = argparse.ArgumentParser(description="BlueDeer 一键初始化")
    parser.add_argument("--venv-dir", default=".venv", help="虚拟目录名称")
    parser.add_argument("--skip-tests", action="store_true", help="跳过测试")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent.parent
    venv_dir = root / args.venv_dir

    print("=" * 60)
    print("BlueDeer 项目初始化")
    print("=" * 60)

    # 1. 创建虚拟环境
    print("\n[1/4] 创建虚拟环境...")
    if not venv_dir.exists():
        run([sys.executable, "-m", "venv", str(venv_dir)])
        print(f"虚拟环境已创建: {venv_dir}")
    else:
        print(f"虚拟环境已存在: {venv_dir}")

    # 确定 pip/python 路径
    if platform.system() == "Windows":
        pip = venv_dir / "Scripts" / "pip.exe"
        python = venv_dir / "Scripts" / "python.exe"
    else:
        pip = venv_dir / "bin" / "pip"
        python = venv_dir / "bin" / "python"

    # 2. 安装依赖
    print("\n[2/4] 安装依赖...")
    req_file = root / "requirements.txt"
    if req_file.exists():
        run([str(pip), "install", "-r", str(req_file)])
    else:
        print("requirements.txt 未找到，跳过依赖安装")

    # 3. 运行测试
    if not args.skip_tests:
        print("\n[3/4] 运行测试...")
        result = run([str(python), "-m", "pytest", "tests/", "-q", "--tb=short"])
        if result.returncode != 0:
            print("测试失败，但初始化继续")
    else:
        print("\n[3/4] 跳过测试")

    # 4. 验证配置
    print("\n[4/4] 验证配置...")
    env_file = root / ".env"
    if not env_file.exists():
        print("警告：.env 文件不存在，请复制 .env.example 并配置")

    print("\n" + "=" * 60)
    print("初始化完成！")
    print(f"激活虚拟环境：{venv_dir}")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
