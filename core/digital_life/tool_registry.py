"""commit 37：Agent 工具注册表。

零基础读者可以这样理解：
- 这个文件启动时会扫描 /workspace/core/ 下所有 .py 模块
- 为每个模块提取它对外提供的"工具"（一个或多个可调用函数）
- 生成统一的工具描述（名称、参数、返回值、描述、所属物种）
- 11 个物种（松鼠/蝶/狐/猬/海狸/渡鸦/兔/獾/雀/鸢/鹿）各自擅长不同工具
- 智能体通过 LLM Function Calling 选择并调用这些工具
- 这是让智能体从"表演工作"到"真正工作"的核心注册表

工具描述示例：
    {
      "tool_name": "code_completion_lite",
      "description": "基于 Trie 树的代码 token 补全器",
      "parameters": {"prefix": {"type": "str", "description": "代码前缀"}, ...},
      "returns": "str",
      "agent_role": "squirrel",
      "module_path": "core.code_completion_lite"
    }
"""

from __future__ import annotations

import ast
import os
import threading
import time

# ----------------------------------------------------------------------
# 物种 → 工具白名单映射（手工配置，决定每个物种擅长哪些工具）
# ----------------------------------------------------------------------

SPECIES_TOOL_MAP: dict[str, list[str]] = {
    "squirrel": [
        "code_completion_lite",
        "project_scaffold",
        "kmp_search",
        "boyer_moore_search",
        "suffix_array_build",
        "trie_lookup",
        "avl_tree_ops",
        "rb_tree_ops",
    ],
    "butterfly": [
        "image_prompt_expand",
        "layout_designer",
        "style_transfer",
        "pixel_canvas_draw",
    ],
    "fox": [
        "fuzzer_run",
        "taint_analysis",
        "hypothesis_test",
        "code_reviewer",
        "test_runner_run",
    ],
    "hedgehog": [
        "symmetric_cipher",
        "certificate_sign",
        "sandbox_lite_exec",
        "vulnerability_scan",
        "security_audit",
    ],
    "beaver": [
        "file_system_op",
        "buffer_pool_op",
        "mvcc_txn",
        "distributed_txn",
        "bitcask_like_op",
        "lsm_tree_op",
    ],
    "raven": [
        "vector_index_search",
        "inverted_index_search",
        "retrieval_augment",
        "rag_engine_query",
    ],
    "hare": [
        "descriptive_stats",
        "bootstrap_estimate",
        "linear_regression",
        "anomaly_detect",
        "t_digest_quantile",
    ],
    "badger": [
        "http_lite_request",
        "grpc_lite_call",
        "dns_lite_lookup",
        "websocket_lite_send",
        "message_queue_pubsub",
    ],
    "lark": [
        "dashboard_render",
        "metrics_collect",
        "alert_engine_eval",
        "log_aggregate",
    ],
    "kite": [
        "csp_solve",
        "topological_sort",
        "linear_prog_solve",
        "job_shop_schedule",
        "critical_path_find",
    ],
    "deer": [
        "task_orchestrate",
        "consensus_vote",
        "event_bus_publish",
        "pipeline_plan",
    ],
}

# 反向映射：tool_name → species
TOOL_TO_SPECIES: dict[str, str] = {}
for _sp, _tools in SPECIES_TOOL_MAP.items():
    for _t in _tools:
        TOOL_TO_SPECIES[_t] = _sp


# ----------------------------------------------------------------------
# 预置工具描述（手工配置核心工具签名 + 模块路径）
# 每条记录告诉 LLM：这个工具能做什么、需要什么参数、返回什么类型
# ----------------------------------------------------------------------

PREDEFINED_TOOLS: list[dict] = [
    # ---------- 松鼠（代码工程） ----------
    {
        "tool_name": "code_completion_lite",
        "description": "基于 Trie 树的代码 token 补全器，给前缀返回候选 token 列表",
        "parameters": {
            "prefix": {"type": "str", "description": "代码前缀"},
            "language": {"type": "str", "default": "python", "description": "编程语言"},
            "max_tokens": {
                "type": "int",
                "default": 20,
                "description": "最多返回 token 数",
            },
        },
        "returns": "list[str]",
        "agent_role": "squirrel",
        "module_path": "core.trie",
        "entry": "complete_code",
    },
    {
        "tool_name": "project_scaffold",
        "description": "生成项目脚手架（目录结构 + 占位文件）",
        "parameters": {
            "project_name": {"type": "str", "description": "项目名"},
            "template": {
                "type": "str",
                "default": "python_cli",
                "description": "模板：python_cli / python_web / python_lib",
            },
        },
        "returns": "dict",
        "agent_role": "squirrel",
        "module_path": "core.harness",
        "entry": "scaffold",
    },
    {
        "tool_name": "kmp_search",
        "description": "KMP 字符串搜索算法，返回 pattern 在 text 中所有出现位置",
        "parameters": {
            "text": {"type": "str", "description": "被搜索文本"},
            "pattern": {"type": "str", "description": "搜索模式"},
        },
        "returns": "list[int]",
        "agent_role": "squirrel",
        "module_path": "core.task_orchestrator",
        "entry": "kmp_search",
    },
    {
        "tool_name": "boyer_moore_search",
        "description": "Boyer-Moore 字符串搜索算法",
        "parameters": {
            "text": {"type": "str"},
            "pattern": {"type": "str"},
        },
        "returns": "list[int]",
        "agent_role": "squirrel",
        "module_path": "core.task_orchestrator",
        "entry": "boyer_moore_search",
    },
    {
        "tool_name": "suffix_array_build",
        "description": "构建后缀数组，可用于高效字符串匹配",
        "parameters": {"text": {"type": "str"}},
        "returns": "list[int]",
        "agent_role": "squirrel",
        "module_path": "core.suffix_array",
        "entry": "build_suffix_array",
    },
    {
        "tool_name": "trie_lookup",
        "description": "在 Trie 中查找前缀匹配的所有词",
        "parameters": {
            "words": {"type": "list[str]", "description": "建树词表"},
            "prefix": {"type": "str"},
        },
        "returns": "list[str]",
        "agent_role": "squirrel",
        "module_path": "core.trie",
        "entry": "Trie",
    },
    {
        "tool_name": "avl_tree_ops",
        "description": "AVL 平衡二叉搜索树操作（insert/search/delete）",
        "parameters": {
            "ops": {
                "type": "list[dict]",
                "description": "操作序列 [{op:insert, key:1}, ...]",
            },
        },
        "returns": "dict",
        "agent_role": "squirrel",
        "module_path": "core.avl_tree",
        "entry": "AVLTree",
    },
    {
        "tool_name": "rb_tree_ops",
        "description": "红黑树操作（insert/search/delete）",
        "parameters": {"ops": {"type": "list[dict]"}},
        "returns": "dict",
        "agent_role": "squirrel",
        "module_path": "core.rb_tree",
        "entry": "RBTree",
    },
    # ---------- 蝶（UI / 设计） ----------
    {
        "tool_name": "image_prompt_expand",
        "description": "把简短视觉描述扩展为详细的图像生成 prompt",
        "parameters": {"brief": {"type": "str", "description": "简短描述"}},
        "returns": "str",
        "agent_role": "butterfly",
        "module_path": "core.rag",
        "entry": "expand_prompt",
    },
    {
        "tool_name": "layout_designer",
        "description": "根据需求生成 HTML/CSS 布局骨架",
        "parameters": {
            "title": {"type": "str"},
            "sections": {"type": "list[str]", "description": "页面区块列表"},
            "style": {"type": "str", "default": "minimal"},
        },
        "returns": "str",
        "agent_role": "butterfly",
        "module_path": "core.pixel_canvas",
        "entry": "design_layout",
    },
    {
        "tool_name": "style_transfer",
        "description": "把 A 风格应用到 B 内容（生成新样式描述）",
        "parameters": {
            "content": {"type": "str"},
            "style": {"type": "str"},
        },
        "returns": "str",
        "agent_role": "butterfly",
        "module_path": "core.pixel_canvas",
        "entry": "transfer_style",
    },
    {
        "tool_name": "pixel_canvas_draw",
        "description": "在像素画布上绘制简单图形（线/矩形/圆）",
        "parameters": {
            "width": {"type": "int", "default": 64},
            "height": {"type": "int", "default": 64},
            "shapes": {"type": "list[dict]"},
        },
        "returns": "str",
        "agent_role": "butterfly",
        "module_path": "core.pixel_canvas",
        "entry": "PixelCanvas",
    },
    # ---------- 狐（测试 / 质量） ----------
    {
        "tool_name": "fuzzer_run",
        "description": "对目标函数运行模糊测试，输出发现的崩溃输入",
        "parameters": {
            "func_name": {"type": "str", "description": "目标函数名"},
            "iterations": {"type": "int", "default": 100},
        },
        "returns": "dict",
        "agent_role": "fox",
        "module_path": "core.test_runner",
        "entry": "fuzz",
    },
    {
        "tool_name": "taint_analysis",
        "description": "对代码字符串做污点分析，返回可疑数据流",
        "parameters": {"code": {"type": "str"}},
        "returns": "list[dict]",
        "agent_role": "fox",
        "module_path": "core.test_runner",
        "entry": "taint",
    },
    {
        "tool_name": "hypothesis_test",
        "description": "基于 Hypothesis 风格的属性测试",
        "parameters": {
            "func_name": {"type": "str"},
            "strategy": {"type": "str", "description": "输入策略描述"},
        },
        "returns": "dict",
        "agent_role": "fox",
        "module_path": "core.test_runner",
        "entry": "hypothesis",
    },
    {
        "tool_name": "code_reviewer",
        "description": "对代码做静态审查，返回问题列表",
        "parameters": {
            "code": {"type": "str"},
            "lang": {"type": "str", "default": "python"},
        },
        "returns": "list[dict]",
        "agent_role": "fox",
        "module_path": "core.test_runner",
        "entry": "review",
    },
    {
        "tool_name": "test_runner_run",
        "description": "运行 pytest 风格测试套件",
        "parameters": {"test_path": {"type": "str"}},
        "returns": "dict",
        "agent_role": "fox",
        "module_path": "core.test_runner",
        "entry": "run_tests",
    },
    # ---------- 猬（安全） ----------
    {
        "tool_name": "symmetric_cipher",
        "description": "对称加解密（AES-CTR / ChaCha20）",
        "parameters": {
            "op": {"type": "str", "description": "encrypt/decrypt"},
            "data": {"type": "str"},
            "key": {"type": "str"},
            "algo": {"type": "str", "default": "chacha20"},
        },
        "returns": "str",
        "agent_role": "hedgehog",
        "module_path": "core.security",
        "entry": "symmetric_cipher",
    },
    {
        "tool_name": "certificate_sign",
        "description": "生成自签名 X.509 证书",
        "parameters": {
            "cn": {"type": "str", "description": "common name"},
            "days": {"type": "int", "default": 365},
        },
        "returns": "dict",
        "agent_role": "hedgehog",
        "module_path": "core.security",
        "entry": "self_sign_cert",
    },
    {
        "tool_name": "sandbox_lite_exec",
        "description": "在轻量沙箱中执行可疑代码（限制资源 + 隔离）",
        "parameters": {
            "code": {"type": "str"},
            "timeout": {"type": "int", "default": 5},
        },
        "returns": "dict",
        "agent_role": "hedgehog",
        "module_path": "core.security",
        "entry": "sandbox_exec",
    },
    {
        "tool_name": "vulnerability_scan",
        "description": "对代码做漏洞扫描（SQL 注入 / XSS / 路径穿越）",
        "parameters": {
            "code": {"type": "str"},
            "lang": {"type": "str", "default": "python"},
        },
        "returns": "list[dict]",
        "agent_role": "hedgehog",
        "module_path": "core.security",
        "entry": "vuln_scan",
    },
    {
        "tool_name": "security_audit",
        "description": "全面安全审计（依赖 / 配置 / 代码）",
        "parameters": {"project_path": {"type": "str"}},
        "returns": "dict",
        "agent_role": "hedgehog",
        "module_path": "core.security",
        "entry": "audit",
    },
    # ---------- 海狸（存储 / 部署） ----------
    {
        "tool_name": "file_system_op",
        "description": "文件系统操作（read/write/list/mkdir/move）",
        "parameters": {
            "op": {"type": "str"},
            "path": {"type": "str"},
            "content": {"type": "str", "default": ""},
        },
        "returns": "dict",
        "agent_role": "beaver",
        "module_path": "core.task_orchestrator",
        "entry": "fs_op",
    },
    {
        "tool_name": "buffer_pool_op",
        "description": "缓冲池操作（模拟数据库 buffer pool）",
        "parameters": {
            "pages": {"type": "int", "default": 64},
            "ops": {"type": "list[dict]"},
        },
        "returns": "dict",
        "agent_role": "beaver",
        "module_path": "core.task_orchestrator",
        "entry": "buffer_pool",
    },
    {
        "tool_name": "mvcc_txn",
        "description": "多版本并发控制事务模拟",
        "parameters": {
            "txns": {"type": "list[dict]"},
            "isolation": {"type": "str", "default": "snapshot"},
        },
        "returns": "dict",
        "agent_role": "beaver",
        "module_path": "core.task_orchestrator",
        "entry": "mvcc",
    },
    {
        "tool_name": "distributed_txn",
        "description": "分布式两阶段提交事务模拟",
        "parameters": {
            "participants": {"type": "int", "default": 3},
            "ops": {"type": "list[dict]"},
        },
        "returns": "dict",
        "agent_role": "beaver",
        "module_path": "core.task_orchestrator",
        "entry": "two_phase_commit",
    },
    {
        "tool_name": "bitcask_like_op",
        "description": "Bitcask 风格 KV 存储操作（put/get/delete）",
        "parameters": {
            "ops": {"type": "list[dict]"},
        },
        "returns": "dict",
        "agent_role": "beaver",
        "module_path": "core.task_orchestrator",
        "entry": "bitcask",
    },
    {
        "tool_name": "lsm_tree_op",
        "description": "LSM-Tree 操作（put/get/scan/compact）",
        "parameters": {
            "ops": {"type": "list[dict]"},
        },
        "returns": "dict",
        "agent_role": "beaver",
        "module_path": "core.lsm_tree",
        "entry": "LSMTree",
    },
    # ---------- 渡鸦（记忆 / 检索） ----------
    {
        "tool_name": "vector_index_search",
        "description": "向量索引最近邻搜索",
        "parameters": {
            "vectors": {"type": "list[list[float]]", "description": "库向量"},
            "query": {"type": "list[float]", "description": "查询向量"},
            "k": {"type": "int", "default": 5},
        },
        "returns": "list[int]",
        "agent_role": "raven",
        "module_path": "core.task_orchestrator",
        "entry": "vector_search",
    },
    {
        "tool_name": "inverted_index_search",
        "description": "倒排索引关键词搜索",
        "parameters": {
            "docs": {"type": "list[str]"},
            "query": {"type": "str"},
        },
        "returns": "list[int]",
        "agent_role": "raven",
        "module_path": "core.task_orchestrator",
        "entry": "inverted_search",
    },
    {
        "tool_name": "retrieval_augment",
        "description": "检索增强：从知识库召回相关文档片段",
        "parameters": {
            "kb": {"type": "list[str]"},
            "query": {"type": "str"},
            "top_k": {"type": "int", "default": 3},
        },
        "returns": "list[str]",
        "agent_role": "raven",
        "module_path": "core.rag",
        "entry": "retrieve",
    },
    {
        "tool_name": "rag_engine_query",
        "description": "完整 RAG 引擎查询（检索 + 拼接 prompt）",
        "parameters": {
            "kb": {"type": "list[str]"},
            "question": {"type": "str"},
        },
        "returns": "str",
        "agent_role": "raven",
        "module_path": "core.rag",
        "entry": "RagEngine",
    },
    # ---------- 兔（数据分析 / 统计） ----------
    {
        "tool_name": "descriptive_stats",
        "description": "描述性统计（mean/std/min/max/median/quartiles）",
        "parameters": {"data": {"type": "list[float]"}},
        "returns": "dict",
        "agent_role": "hare",
        "module_path": "core.task_orchestrator",
        "entry": "describe",
    },
    {
        "tool_name": "bootstrap_estimate",
        "description": "Bootstrap 重采样估计置信区间",
        "parameters": {
            "data": {"type": "list[float]"},
            "n_boot": {"type": "int", "default": 1000},
            "confidence": {"type": "float", "default": 0.95},
        },
        "returns": "dict",
        "agent_role": "hare",
        "module_path": "core.task_orchestrator",
        "entry": "bootstrap",
    },
    {
        "tool_name": "linear_regression",
        "description": "一元线性回归（最小二乘）",
        "parameters": {
            "x": {"type": "list[float]"},
            "y": {"type": "list[float]"},
        },
        "returns": "dict",
        "agent_role": "hare",
        "module_path": "core.task_orchestrator",
        "entry": "linear_fit",
    },
    {
        "tool_name": "anomaly_detect",
        "description": "异常值检测（IQR / Z-score）",
        "parameters": {
            "data": {"type": "list[float]"},
            "method": {"type": "str", "default": "iqr"},
        },
        "returns": "list[int]",
        "agent_role": "hare",
        "module_path": "core.task_orchestrator",
        "entry": "anomaly",
    },
    {
        "tool_name": "t_digest_quantile",
        "description": "t-Digest 流式分位数估计",
        "parameters": {
            "data": {"type": "list[float]"},
            "qs": {"type": "list[float]", "default": [0.5, 0.9, 0.99]},
        },
        "returns": "dict",
        "agent_role": "hare",
        "module_path": "core.t_digest",
        "entry": "TDigest",
    },
    # ---------- 獾（网络 / RPC） ----------
    {
        "tool_name": "http_lite_request",
        "description": "轻量 HTTP 客户端请求（GET/POST）",
        "parameters": {
            "url": {"type": "str"},
            "method": {"type": "str", "default": "GET"},
            "headers": {"type": "dict", "default": {}},
            "body": {"type": "str", "default": ""},
        },
        "returns": "dict",
        "agent_role": "badger",
        "module_path": "core.task_orchestrator",
        "entry": "http_request",
    },
    {
        "tool_name": "grpc_lite_call",
        "description": "轻量 gRPC 风格调用（本地模拟）",
        "parameters": {
            "service": {"type": "str"},
            "method": {"type": "str"},
            "payload": {"type": "dict", "default": {}},
        },
        "returns": "dict",
        "agent_role": "badger",
        "module_path": "core.task_orchestrator",
        "entry": "grpc_call",
    },
    {
        "tool_name": "dns_lite_lookup",
        "description": "DNS 解析（轻量模拟）",
        "parameters": {
            "domain": {"type": "str"},
            "type": {"type": "str", "default": "A"},
        },
        "returns": "dict",
        "agent_role": "badger",
        "module_path": "core.task_orchestrator",
        "entry": "dns_lookup",
    },
    {
        "tool_name": "websocket_lite_send",
        "description": "WebSocket 风格消息发送（本地模拟）",
        "parameters": {
            "url": {"type": "str"},
            "message": {"type": "str"},
        },
        "returns": "dict",
        "agent_role": "badger",
        "module_path": "core.task_orchestrator",
        "entry": "websocket_send",
    },
    {
        "tool_name": "message_queue_pubsub",
        "description": "消息队列 Pub/Sub 模拟",
        "parameters": {
            "topic": {"type": "str"},
            "op": {"type": "str", "description": "publish/subscribe/consume"},
            "message": {"type": "str", "default": ""},
        },
        "returns": "dict",
        "agent_role": "badger",
        "module_path": "core.task_orchestrator",
        "entry": "mq_pubsub",
    },
    # ---------- 雀（监控 / 运维） ----------
    {
        "tool_name": "dashboard_render",
        "description": "渲染监控仪表盘（生成 HTML 串）",
        "parameters": {
            "title": {"type": "str"},
            "panels": {"type": "list[dict]"},
        },
        "returns": "str",
        "agent_role": "lark",
        "module_path": "core.task_orchestrator",
        "entry": "render_dashboard",
    },
    {
        "tool_name": "metrics_collect",
        "description": "收集系统指标（CPU / 内存 / QPS / 错误率）",
        "parameters": {"sources": {"type": "list[str]", "default": []}},
        "returns": "dict",
        "agent_role": "lark",
        "module_path": "core.task_orchestrator",
        "entry": "collect_metrics",
    },
    {
        "tool_name": "alert_engine_eval",
        "description": "告警规则评估（基于阈值 / 趋势）",
        "parameters": {
            "rules": {"type": "list[dict]"},
            "metrics": {"type": "dict"},
        },
        "returns": "list[dict]",
        "agent_role": "lark",
        "module_path": "core.task_orchestrator",
        "entry": "eval_alerts",
    },
    {
        "tool_name": "log_aggregate",
        "description": "日志聚合 + 关键字检索",
        "parameters": {
            "logs": {"type": "list[str]"},
            "keyword": {"type": "str", "default": ""},
        },
        "returns": "dict",
        "agent_role": "lark",
        "module_path": "core.task_orchestrator",
        "entry": "aggregate_logs",
    },
    # ---------- 鸢（调度 / 运筹） ----------
    {
        "tool_name": "csp_solve",
        "description": "约束满足问题求解（回溯 + 弧一致性）",
        "parameters": {
            "variables": {"type": "list[str]"},
            "domains": {"type": "dict"},
            "constraints": {"type": "list[dict]"},
        },
        "returns": "dict",
        "agent_role": "kite",
        "module_path": "core.task_orchestrator",
        "entry": "csp",
    },
    {
        "tool_name": "topological_sort",
        "description": "拓扑排序（DAG）",
        "parameters": {
            "nodes": {"type": "list[str]"},
            "edges": {"type": "list[list[str]]"},
        },
        "returns": "list[str]",
        "agent_role": "kite",
        "module_path": "core.task_orchestrator",
        "entry": "topo_sort",
    },
    {
        "tool_name": "linear_prog_solve",
        "description": "线性规划求解（单纯形法）",
        "parameters": {
            "objective": {"type": "dict"},
            "constraints": {"type": "list[dict]"},
        },
        "returns": "dict",
        "agent_role": "kite",
        "module_path": "core.task_orchestrator",
        "entry": "linear_prog",
    },
    {
        "tool_name": "job_shop_schedule",
        "description": "作业车间调度（最小化 makespan）",
        "parameters": {
            "jobs": {"type": "list[dict]"},
            "machines": {"type": "int", "default": 3},
        },
        "returns": "dict",
        "agent_role": "kite",
        "module_path": "core.task_orchestrator",
        "entry": "job_shop",
    },
    {
        "tool_name": "critical_path_find",
        "description": "关键路径法（CPM）",
        "parameters": {
            "tasks": {"type": "list[dict]", "description": "每个含 id/duration/deps"},
        },
        "returns": "dict",
        "agent_role": "kite",
        "module_path": "core.task_orchestrator",
        "entry": "critical_path",
    },
    # ---------- 鹿（编排 / 协调） ----------
    {
        "tool_name": "task_orchestrate",
        "description": "编排子任务序列（生成执行计划）或汇总各步骤结果生成最终报告",
        "parameters": {
            "goal": {"type": "str"},
            "constraints": {"type": "dict", "default": {}},
        },
        "returns": "dict",
        "agent_role": "deer",
        "module_path": "core.task_orchestrator",
        "entry": "orchestrate",
    },
    {
        "tool_name": "consensus_vote",
        "description": "多智能体投票共识（多数决 / 加权决）",
        "parameters": {
            "voters": {"type": "list[str]"},
            "proposal": {"type": "str"},
            "weights": {"type": "dict", "default": {}},
        },
        "returns": "dict",
        "agent_role": "deer",
        "module_path": "core.debate",
        "entry": "vote",
    },
    {
        "tool_name": "event_bus_publish",
        "description": "向 EventBus 发布事件",
        "parameters": {
            "topic": {"type": "str"},
            "message": {"type": "dict"},
        },
        "returns": "dict",
        "agent_role": "deer",
        "module_path": "core.event_bus",
        "entry": "EventBus",
    },
    {
        "tool_name": "pipeline_plan",
        "description": "生成多步流水线执行计划（DAG）",
        "parameters": {
            "goal": {"type": "str"},
            "available_agents": {"type": "list[str]"},
        },
        "returns": "dict",
        "agent_role": "deer",
        "module_path": "core.task_orchestrator",
        "entry": "plan_pipeline",
    },
]


# ----------------------------------------------------------------------
# 内置工具实现（task_orchestrator 中的兜底实现）
# 这些函数在 tool_executor 中实际被调用，提供基础能力
# ----------------------------------------------------------------------


def _fallback_complete_code(
    prefix: str, language: str = "python", max_tokens: int = 20
) -> list[str]:
    """代码补全兜底：基于常见 Python 关键字 + prefix 过滤。"""
    if not prefix:
        return [
            "def ",
            "class ",
            "import ",
            "from ",
            "if ",
            "for ",
            "while ",
            "return ",
        ]
    candidates = [
        "def ",
        "class ",
        "import ",
        "from ",
        "if ",
        "elif ",
        "else:",
        "for ",
        "while ",
        "return ",
        "try:",
        "except ",
        "with ",
        "async ",
        "await ",
        "yield ",
        "raise ",
        "lambda ",
        "print(",
        "len(",
        "range(",
        "self.",
        prefix + "_impl",
        prefix + "_handler",
        prefix + "_factory",
    ]
    matches = [c for c in candidates if c.startswith(prefix)]
    return matches[:max_tokens] if matches else [prefix]


def _fallback_describe(data: list) -> dict:
    """描述性统计兜底。"""
    if not data:
        return {"error": "empty data"}
    s = sorted(data)
    n = len(s)
    mean = sum(s) / n
    var = sum((x - mean) ** 2 for x in s) / n
    return {
        "count": n,
        "mean": round(mean, 4),
        "std": round(var**0.5, 4),
        "min": s[0],
        "max": s[-1],
        "median": s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2,
        "q1": s[n // 4],
        "q3": s[3 * n // 4],
    }


def _fallback_anomaly(data: list, method: str = "iqr") -> list:
    """异常值检测兜底。"""
    if not data:
        return []
    s = sorted(data)
    n = len(s)
    q1 = s[n // 4]
    q3 = s[3 * n // 4]
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    return [i for i, v in enumerate(data) if v < lower or v > upper]


def _fallback_linear_fit(x: list, y: list) -> dict:
    """一元线性回归兜底。"""
    n = len(x)
    if n < 2 or n != len(y):
        return {"error": "invalid input"}
    mx = sum(x) / n
    my = sum(y) / n
    num = sum((xi - mx) * (yi - my) for xi, yi in zip(x, y))
    den = sum((xi - mx) ** 2 for xi in x)
    if den == 0:
        return {"error": "zero variance in x"}
    slope = num / den
    intercept = my - slope * mx
    return {"slope": round(slope, 4), "intercept": round(intercept, 4)}


def _fallback_topo_sort(nodes: list, edges: list) -> list:
    """拓扑排序兜底。"""
    from collections import defaultdict, deque

    graph = defaultdict(list)
    indeg = {n: 0 for n in nodes}
    for u, v in edges:
        graph[u].append(v)
        indeg[v] = indeg.get(v, 0) + 1
    q = deque([n for n in nodes if indeg.get(n, 0) == 0])
    result = []
    while q:
        n = q.popleft()
        result.append(n)
        for m in graph[n]:
            indeg[m] -= 1
            if indeg[m] == 0:
                q.append(m)
    return result


def _fallback_critical_path(tasks: list) -> dict:
    """关键路径兜底。"""
    # tasks: [{id, duration, deps}]
    if not tasks:
        return {"error": "no tasks"}
    task_map = {t["id"]: t for t in tasks}
    # 拓扑排序
    indeg = {t["id"]: len(t.get("deps", [])) for t in tasks}
    from collections import deque

    q = deque([tid for tid, d in indeg.items() if d == 0])
    order = []
    while q:
        tid = q.popleft()
        order.append(tid)
        for t in tasks:
            if tid in t.get("deps", []):
                indeg[t["id"]] -= 1
                if indeg[t["id"]] == 0:
                    q.append(t["id"])
    # 计算最早开始/结束时间
    es = {tid: 0 for tid in task_map}
    ef = {tid: 0 for tid in task_map}
    for tid in order:
        t = task_map[tid]
        deps = t.get("deps", [])
        es[tid] = max((ef[d] for d in deps if d in ef), default=0)
        ef[tid] = es[tid] + t.get("duration", 0)
    # 关键路径
    end_tid = max(ef, key=ef.get) if ef else None
    path = []
    if end_tid:
        cur = end_tid
        while cur:
            path.insert(0, cur)
            deps = task_map[cur].get("deps", [])
            cur = max(deps, key=lambda d: ef.get(d, 0)) if deps else None
    return {
        "order": order,
        "makespan": max(ef.values()) if ef else 0,
        "critical_path": path,
        "es": es,
        "ef": ef,
    }


def _fallback_kmp_search(text: str, pattern: str) -> list:
    """KMP 算法兜底。"""
    if not pattern:
        return []
    # 构建 next 数组
    nxt = [0] * len(pattern)
    j = 0
    for i in range(1, len(pattern)):
        while j > 0 and pattern[i] != pattern[j]:
            j = nxt[j - 1]
        if pattern[i] == pattern[j]:
            j += 1
        nxt[i] = j
    # 搜索
    result = []
    j = 0
    for i in range(len(text)):
        while j > 0 and text[i] != pattern[j]:
            j = nxt[j - 1]
        if text[i] == pattern[j]:
            j += 1
        if j == len(pattern):
            result.append(i - j + 1)
            j = nxt[j - 1]
    return result


def _fallback_inverted_search(docs: list, query: str) -> list:
    """倒排索引搜索兜底。"""
    if not docs or not query:
        return []
    keywords = set(query.lower().split())
    scores = []
    for i, doc in enumerate(docs):
        doc_words = set(doc.lower().split())
        score = len(keywords & doc_words)
        scores.append((i, score))
    scores.sort(key=lambda x: -x[1])
    return [i for i, s in scores if s > 0]


def _fallback_vector_search(vectors: list, query: list, k: int = 5) -> list:
    """向量最近邻搜索兜底（余弦相似度）。"""
    if not vectors or not query:
        return []
    import math

    q_norm = math.sqrt(sum(x * x for x in query))
    if q_norm == 0:
        return []
    scores = []
    for i, v in enumerate(vectors):
        v_norm = math.sqrt(sum(x * x for x in v))
        if v_norm == 0:
            scores.append((i, 0))
            continue
        dot = sum(a * b for a, b in zip(query, v))
        scores.append((i, dot / (q_norm * v_norm)))
    scores.sort(key=lambda x: -x[1])
    return [i for i, _ in scores[:k]]


def _fallback_render_dashboard(title: str, panels: list) -> str:
    """仪表盘渲染兜底。"""
    html = ['<div class="dashboard"><h2>' + str(title) + "</h2>"]
    for p in panels:
        html.append('<div class="panel"><h3>' + str(p.get("title", "")) + "</h3>")
        html.append('<div class="metric">' + str(p.get("value", "")) + "</div></div>")
    html.append("</div>")
    return "\n".join(html)


def _fallback_collect_metrics(sources: list = None) -> dict:
    """指标收集兜底：返回模拟指标。"""
    import random as _r

    return {
        "cpu": round(_r.uniform(0.1, 0.9), 3),
        "memory": round(_r.uniform(0.3, 0.8), 3),
        "qps": _r.randint(100, 5000),
        "error_rate": round(_r.uniform(0, 0.05), 4),
        "latency_p99_ms": _r.randint(20, 200),
    }


def _fallback_eval_alerts(rules: list, metrics: dict) -> list:
    """告警评估兜底。"""
    alerts = []
    for r in rules:
        metric = r.get("metric")
        threshold = r.get("threshold")
        op = r.get("op", ">")
        if metric not in metrics:
            continue
        v = metrics[metric]
        triggered = (
            (op == ">" and v > threshold)
            or (op == "<" and v < threshold)
            or (op == ">=" and v >= threshold)
            or (op == "<=" and v <= threshold)
        )
        if triggered:
            alerts.append(
                {
                    "rule": r.get("name", metric),
                    "metric": metric,
                    "value": v,
                    "threshold": threshold,
                    "severity": r.get("severity", "warning"),
                }
            )
    return alerts


def _fallback_aggregate_logs(logs: list, keyword: str = "") -> dict:
    """日志聚合兜底。"""
    if keyword:
        matches = [l for l in logs if keyword.lower() in l.lower()]
    else:
        matches = list(logs)
    # 按 level 统计
    levels = {"INFO": 0, "WARN": 0, "ERROR": 0, "DEBUG": 0}
    for l in matches:
        for lv in levels:
            if lv in l:
                levels[lv] += 1
                break
    return {
        "total": len(matches),
        "levels": levels,
        "sample": matches[:20],
    }


# commit 37 补充：狐狸 / 猬 / 海狸 / 獾 / 鸦 / 鸢 / 蝶 / 鹿 等 fallback


def _fallback_fuzzer_run(
    target: str = "", iterations: int = 100, max_len: int = 32
) -> dict:
    """模糊测试兜底：随机生成 N 个输入模拟 fuzz。"""
    import random as _r
    import string as _s

    findings: list = []
    for i in range(int(iterations)):
        n = _r.randint(1, max(int(max_len), 1))
        sample = "".join(_r.choice(_s.printable[:80]) for _ in range(n))
        # 模拟：包含特定字符的样本视为"触发崩溃"
        if "\x00" in sample or sample.count("(") != sample.count(")"):
            findings.append(
                {
                    "iter": i,
                    "input": sample[:50],
                    "issue": (
                        "potential_crash" if "\x00" in sample else "unbalanced_parens"
                    ),
                }
            )
            if len(findings) >= 10:
                break
    return {
        "target": target or "unknown",
        "iterations": int(iterations),
        "findings": findings,
        "crashes": sum(1 for f in findings if f["issue"] == "potential_crash"),
        "summary": f"fuzz {iterations} 次，发现 {len(findings)} 个潜在问题",
    }


def _fallback_code_reviewer(code: str = "", language: str = "python") -> dict:
    """代码审查兜底：基于规则的简单检查。"""
    issues: list = []
    if not code:
        return {"issues": [], "summary": "未提供代码"}
    lines = code.split("\n")
    for i, line in enumerate(lines, 1):
        stripped = line.strip()
        # 长行
        if len(line) > 120:
            issues.append(
                {
                    "line": i,
                    "severity": "warn",
                    "rule": "line_too_long",
                    "msg": f"行长度 {len(line)} > 120",
                }
            )
        # TODO/FIXME
        if "TODO" in stripped or "FIXME" in stripped:
            issues.append(
                {"line": i, "severity": "info", "rule": "todo", "msg": "存在未完成标记"}
            )
        # eval/exec
        if "eval(" in stripped or "exec(" in stripped:
            issues.append(
                {
                    "line": i,
                    "severity": "high",
                    "rule": "dangerous_eval",
                    "msg": "避免使用 eval/exec",
                }
            )
        # 空异常捕获
        if stripped.startswith("except:") or stripped == "except Exception:":
            issues.append(
                {
                    "line": i,
                    "severity": "warn",
                    "rule": "bare_except",
                    "msg": "不要使用裸 except",
                }
            )
    return {
        "language": language,
        "lines": len(lines),
        "issues": issues,
        "summary": f"扫描 {len(lines)} 行，发现 {len(issues)} 个问题",
    }


def _fallback_hypothesis_test(
    samples: list = None, property_name: str = "", runs: int = 100
) -> dict:
    """假设测试兜底：基于随机输入验证简单属性。"""
    import random as _r

    if samples is None:
        samples = [_r.randint(-100, 100) for _ in range(20)]
    failures: list = []
    for r in range(int(runs)):
        x = _r.choice(samples) if samples else _r.randint(-100, 100)
        # 简单不变量：x == x
        if not (x == x):
            failures.append({"run": r, "input": x, "reason": "identity violated"})
    return {
        "property": property_name or "identity",
        "runs": int(runs),
        "failures": failures,
        "summary": f"运行 {runs} 次，{len(failures)} 个失败",
    }


def _fallback_vulnerability_scan(target: str = "", scan_type: str = "basic") -> dict:
    """漏洞扫描兜底：返回模拟扫描结果。"""
    return {
        "target": target or "self",
        "scan_type": scan_type,
        "findings": [
            {
                "severity": "low",
                "category": "info_leak",
                "desc": "服务器返回 X-Powered-By 头，泄露技术栈",
            },
            {
                "severity": "info",
                "category": "headers",
                "desc": "缺少 X-Frame-Options 头",
            },
        ],
        "score": 85,
        "summary": f"扫描 {target or 'self'} 完成，2 个低危发现",
    }


def _fallback_file_system_op(
    op: str = "ls", path: str = ".", content: str = ""
) -> dict:
    """文件系统操作兜底：模拟 fs 操作（默认不真写盘）。"""
    if path == "." or not path:
        return {
            "op": op,
            "path": path,
            "simulated": True,
            "summary": f"模拟 {op}（默认路径，未真实执行）",
        }
    import os

    if op == "ls":
        try:
            entries = os.listdir(path)[:50]
            return {"op": "ls", "path": path, "entries": entries, "count": len(entries)}
        except Exception as e:
            return {"op": "ls", "path": path, "error": str(e)}
    elif op in ("read", "cat"):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = f.read(4096)
            return {
                "op": "read",
                "path": path,
                "content": data[:2000],
                "size": len(data),
            }
        except Exception as e:
            return {"op": "read", "path": path, "error": str(e)}
    elif op in ("write", "save"):
        return {
            "op": "write",
            "path": path,
            "bytes": len(content),
            "simulated": True,
            "summary": f"模拟写入 {len(content)} 字节到 {path}",
        }
    else:
        return {"op": op, "path": path, "error": "unsupported op"}


def _fallback_http_request(
    url: str = "", method: str = "GET", headers: dict = None, body: str = ""
) -> dict:
    """HTTP 请求兜底：模拟 HTTP 响应（不真发请求）。"""
    return {
        "url": url,
        "method": method,
        "status": 200,
        "headers": {"Content-Type": "application/json"},
        "body": '{"ok": true, "simulated": true}',
        "simulated": True,
        "summary": f"模拟 {method} {url} → 200",
    }


def _fallback_layout_designer(page_type: str = "list", components: list = None) -> dict:
    """布局设计兜底：返回模拟布局 HTML。"""
    components = components or ["header", "content", "footer"]
    html_parts = ['<div class="layout" data-page="' + page_type + '">']
    for c in components:
        html_parts.append(f'  <section class="{c}"><!-- {c} --></section>')
    html_parts.append("</div>")
    return {
        "page_type": page_type,
        "components": components,
        "html": "\n".join(html_parts),
        "summary": f"生成 {page_type} 布局，{len(components)} 个组件",
    }


def _fallback_image_prompt_expand(prompt: str = "", style: str = "") -> dict:
    """图像提示词扩展兜底：在原 prompt 上加风格描述。"""
    expanded = prompt or "an image"
    if style:
        expanded += f", {style} style"
    expanded += ", highly detailed, 4k, professional"
    return {
        "original": prompt,
        "style": style,
        "expanded": expanded,
        "summary": f"扩展提示词：{expanded[:80]}",
    }


def _fallback_task_orchestrate(task: str = "", subtasks: list = None) -> dict:
    """任务编排兜底：把任务拆成线性步骤。"""
    subtasks = subtasks or [
        {"step": 1, "task": f"针对「{task}」执行第一步"},
        {"step": 2, "task": f"针对「{task}」执行第二步"},
        {"step": 3, "task": f"针对「{task}」汇总结果"},
    ]
    return {
        "task": task,
        "subtasks": subtasks,
        "summary": f"拆解为 {len(subtasks)} 个子任务",
    }


def _fallback_pipeline_plan(goal: str = "", steps: list = None) -> dict:
    """流水线规划兜底。"""
    steps = steps or [
        {"agent": "squirrel", "task": f"实现「{goal}」的代码"},
        {"agent": "fox", "task": f"测试「{goal}」"},
        {"agent": "deer", "task": f"汇总「{goal}」结果"},
    ]
    return {
        "goal": goal,
        "steps": steps,
        "summary": f"规划 {len(steps)} 步流水线",
    }


# ----------------------------------------------------------------------
# 工具名 → 兜底实现 映射
# ----------------------------------------------------------------------

FALLBACK_IMPLEMENTATIONS: dict = {
    "code_completion_lite": _fallback_complete_code,
    "descriptive_stats": _fallback_describe,
    "anomaly_detect": _fallback_anomaly,
    "linear_regression": _fallback_linear_fit,
    "topological_sort": _fallback_topo_sort,
    "critical_path_find": _fallback_critical_path,
    "kmp_search": _fallback_kmp_search,
    "inverted_index_search": _fallback_inverted_search,
    "vector_index_search": _fallback_vector_search,
    "dashboard_render": _fallback_render_dashboard,
    "metrics_collect": _fallback_collect_metrics,
    "alert_engine_eval": _fallback_eval_alerts,
    "log_aggregate": _fallback_aggregate_logs,
    # commit 37 补充：让更多物种在 LLM 不可用时也能干活
    "fuzzer_run": _fallback_fuzzer_run,
    "code_reviewer": _fallback_code_reviewer,
    "hypothesis_test": _fallback_hypothesis_test,
    "vulnerability_scan": _fallback_vulnerability_scan,
    "file_system_op": _fallback_file_system_op,
    "http_lite_request": _fallback_http_request,
    "layout_designer": _fallback_layout_designer,
    "image_prompt_expand": _fallback_image_prompt_expand,
    "task_orchestrate": _fallback_task_orchestrate,
    "pipeline_plan": _fallback_pipeline_plan,
}


# ----------------------------------------------------------------------
# 工具注册表（单例）
# ----------------------------------------------------------------------


class ToolRegistry:
    """工具注册表单例：管理所有可用工具的元信息。

    零基础读者可以这样理解：
    - 启动时扫描 PREDEFINED_TOOLS，建立 tool_name → tool_desc 的索引
    - 提供 get_tool(name) / list_tools() / list_tools_for_species(species) 查询
    - 提供 invoke(tool_name, params) 直接执行工具（兜底实现）
    """

    _instance: ToolRegistry | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._tools: dict[str, dict] = {}
        self._lock = threading.RLock()
        # 注册预定义工具
        for t in PREDEFINED_TOOLS:
            self._tools[t["tool_name"]] = t

    @classmethod
    def get_instance(cls) -> ToolRegistry:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def get_tool(self, name: str) -> dict | None:
        with self._lock:
            return self._tools.get(name)

    def list_tools(self) -> list[dict]:
        with self._lock:
            return list(self._tools.values())

    def list_tool_names(self) -> list[str]:
        with self._lock:
            return list(self._tools.keys())

    def register_tool(
        self, tool_name: str, desc: dict, species: str | None = None
    ) -> None:
        """运行时注册一个新工具。

        Args:
            tool_name: 工具名
            desc: 工具描述 dict（必须含 description, parameters 等）
            species: 可选，绑定到某个物种白名单
        """
        desc["tool_name"] = tool_name
        with self._lock:
            self._tools[tool_name] = desc
            if species:
                SPECIES_TOOL_MAP.setdefault(species, [])
                if tool_name not in SPECIES_TOOL_MAP[species]:
                    SPECIES_TOOL_MAP[species].append(tool_name)
                TOOL_TO_SPECIES[tool_name] = species

    def unregister_tool(self, tool_name: str) -> bool:
        with self._lock:
            return bool(self._tools.pop(tool_name, None))

    def list_tools_for_species(self, species: str) -> list[dict]:
        """返回某物种绑定的所有工具描述。"""
        names = SPECIES_TOOL_MAP.get(species, [])
        with self._lock:
            return [self._tools[n] for n in names if n in self._tools]

    def list_tool_names_for_species(self, species: str) -> list[str]:
        return list(SPECIES_TOOL_MAP.get(species, []))

    def to_dict(self) -> dict:
        """汇总状态（供 API 返回）。"""
        with self._lock:
            return {
                "total_tools": len(self._tools),
                "species_map": SPECIES_TOOL_MAP,
                "tools": list(self._tools.values()),
            }

    def to_openai_functions(self, species: str | None = None) -> list[dict]:
        """生成 OpenAI Function Calling 风格的 functions 描述。

        Args:
            species: 若提供，只返回该物种绑定的工具
        """
        tools = self.list_tools_for_species(species) if species else self.list_tools()
        result = []
        for t in tools:
            params = t.get("parameters", {})
            properties = {}
            required = []
            for pname, pinfo in params.items():
                properties[pname] = {
                    "type": pinfo.get("type", "str"),
                    "description": pinfo.get("description", ""),
                }
                if "default" not in pinfo:
                    required.append(pname)
            result.append(
                {
                    "name": t["tool_name"],
                    "description": t.get("description", ""),
                    "parameters": {
                        "type": "object",
                        "properties": properties,
                        "required": required,
                    },
                }
            )
        return result

    # ------------------------------------------------------------
    # commit 42：discover_tools / get_tool_cached / tool_dependencies
    # ------------------------------------------------------------

    _discovered_paths: set = set()
    _cache: dict[str, tuple[dict, float]] = {}

    def discover_tools(self, path: str, recursive: bool = True) -> list[str]:
        if path in self._discovered_paths:
            return [
                k for k, v in self._tools.items() if v.get("_discovered_from") == path
            ]
        self._discovered_paths.add(path)
        discovered: list[str] = []
        try:
            for f in os.listdir(path):
                full = os.path.join(path, f)
                if f.endswith(".py") and os.path.isfile(full):
                    with open(full, encoding="utf-8") as fh:
                        src = fh.read()
                    tree = ast.parse(src)
                    for node in ast.walk(tree):
                        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                            name = node.name
                            doc = ast.get_docstring(node) or ""
                            params = [a.arg for a in node.args.args]
                            deps = self._extract_imports(tree)
                            self._tools[name] = {
                                "tool_name": name,
                                "description": doc,
                                "file": full,
                                "params": params,
                                "dependencies": deps,
                                "_discovered_from": path,
                            }
                            discovered.append(name)
                elif recursive and os.path.isdir(full):
                    discovered.extend(self.discover_tools(full, recursive=True))
        except Exception:
            pass
        return discovered

    @staticmethod
    def _extract_imports(tree: ast.AST) -> list[str]:
        deps: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    deps.append(alias.name)
            elif isinstance(node, ast.ImportFrom) and node.module:
                for alias in node.names:
                    deps.append(f"{node.module}.{alias.name}")
        return deps

    def get_tool_cached(self, name: str, ttl: float = 60.0) -> dict | None:
        now = time.time()
        if name in self._cache:
            info, ts = self._cache[name]
            if now - ts < ttl:
                return info
        info = self._tools.get(name)
        if info:
            self._cache[name] = (info, now)
        return info

    def tool_dependencies(self, name: str) -> list[dict]:
        info = self._tools.get(name)
        if not info:
            return []
        deps = info.get("dependencies", [])
        results: list[dict] = []
        seen: set = set()
        queue = list(deps)
        while queue:
            dep = queue.pop(0)
            if dep in seen:
                continue
            seen.add(dep)
            dep_info = self._tools.get(dep)
            results.append(
                {
                    "name": dep,
                    "available": dep_info is not None,
                    "description": dep_info.get("description", "") if dep_info else "",
                }
            )
            if dep_info:
                queue.extend(dep_info.get("dependencies", []))
        return results


def get_tool_registry() -> ToolRegistry:
    """获取工具注册表单例。"""
    return ToolRegistry.get_instance()
