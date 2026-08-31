# -*- coding: utf-8 -*-
"""Agent 池核心：多实例管理、健康检查、自动故障切换、真实 LLM 调用。"""

import json
import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

logger = logging.getLogger("bluedeer.agent_pool")

# 全局 LLM 配置（从 agent/config.json 加载）
_GLOB_LLM = {"base": "", "model": "", "key": ""}

class AgentStatus(str, Enum):
    OFFLINE = "offline"
    ONLINE = "online"
    BUSY = "busy"
    ERROR = "error"

_SYSTEM_PROMPTS = {
    "general": "你是 BlueDeer 通用助手，擅长日常问答、办公辅助、信息整理。回答简洁实用。",
    "code": "你是 BlueDeer 高级代码助手，精通 Python/JS/TS。擅长写代码、调试、重构、解释原理。回答直接给出代码，附简要说明。",
    "review": "你是 BlueDeer 代码审查专家，擅长发现 bug、安全问题、性能瓶颈和代码规范问题。给出具体位置和修复建议。",
    "text": "你是 BlueDeer 文本处理专家，擅长文档生成、翻译、摘要、润色。根据要求输出高质量文本。",
    "video": "你是 BlueDeer 视频生成助手，擅长视频脚本撰写、分镜设计、创意构思。",
    "image": "你是 BlueDeer 图片生成助手，擅长图像描述优化、提示词工程、风格分析。",
    "audio": "你是 BlueDeer 语音合成助手，擅长文本转语音优化、语音克隆建议、音效设计。",
}

@dataclass
class AgentInstance:
    id: str
    name: str
    description: str
    scene: str
    api_base: str
    api_model: str
    api_key: str
    icon: str = "🤖"
    status: AgentStatus = AgentStatus.OFFLINE
    last_heartbeat: float = 0.0
    error_count: int = 0
    success_count: int = 0
    config: dict = field(default_factory=dict)
    history: list = field(default_factory=list)  # 对话历史
    llm_base: str = ""
    llm_model: str = ""
    llm_key: str = ""

    def to_dict(self) -> dict:
        return {
            "id": self.id, "name": self.name, "description": self.description,
            "scene": self.scene, "api_base": self.api_base, "api_model": self.api_model,
            "icon": self.icon, "status": self.status.value,
            "last_heartbeat": self.last_heartbeat,
            "error_count": self.error_count, "success_count": self.success_count,
            "history_size": len(self.history),
            "config": self.config,
        }

    def scene_label(self) -> str:
        m = {"video":"🎬 视频生成","image":"🖼️ 图片生成","audio":"🔊 语音合成",
             "text":"📝 文本处理","code":"💻 代码助手","review":"🔍 代码审查","general":"🧠 通用助手"}
        return m.get(self.scene, self.scene)

    def mark_online(self):
        self.status = AgentStatus.ONLINE; self.last_heartbeat = time.time(); self.error_count = 0
    def mark_busy(self):
        self.status = AgentStatus.BUSY; self.last_heartbeat = time.time()
    def mark_error(self):
        self.error_count += 1; self.status = AgentStatus.ERROR; self.last_heartbeat = time.time()
    def mark_success(self):
        self.success_count += 1; self.status = AgentStatus.ONLINE; self.last_heartbeat = time.time()
    def mark_offline(self):
        self.status = AgentStatus.OFFLINE; self.last_heartbeat = 0.0


class AgentPool:
    def __init__(self, config_path: Optional[str] = None):
        self._instances: dict[str, AgentInstance] = {}
        self._lock = threading.RLock()
        self._current_id: Optional[str] = None
        self._auto_failover = True
        self._failover_timeout = 30
        self._health_check_interval = 10
        self._load_global_llm_config()
        if config_path:
            self.load_config(config_path)
        else:
            self._load_builtin()
        self._start_health_checker()

    def _load_global_llm_config(self):
        """从 agent/config.json 加载全局 LLM 配置。"""
        global _GLOB_LLM
        cfg_path = Path(__file__).parent.parent / "agent" / "config.json"
        if cfg_path.exists():
            try:
                data = json.loads(cfg_path.read_text(encoding="utf-8"))
                _GLOB_LLM = {
                    "base": data.get("api_base", ""),
                    "model": data.get("api_model", ""),
                    "key": data.get("api_key", ""),
                }
                logger.info("全局 LLM 配置已加载: model=%s", _GLOB_LLM["model"])
            except Exception as e:
                logger.warning("加载 LLM 配置失败: %s", e)

    def _load_builtin(self):
        builtin = [
            AgentInstance("general_01","通用助手","通用问答、文本处理、日常办公","general","","agnes-2.5-flash","","🧠"),
            AgentInstance("code_01","代码助手","写代码、调试、重构、Code Review","code","","agnes-2.5-flash","","💻"),
            AgentInstance("review_01","代码审查","静态分析、安全检查、性能审查","review","","agnes-2.5-flash","","🔍"),
            AgentInstance("text_01","文本处理","文档生成、翻译、摘要、润色","text","","agnes-2.5-flash","","📝"),
            AgentInstance("video_01","视频生成","AI 视频生成、动画制作、特效处理","video","","","","🎬"),
            AgentInstance("image_01","图片生成","AI 绘图、图像编辑、风格转换","image","","","","🖼️"),
            AgentInstance("audio_01","语音合成","文字转语音、语音克隆、音效生成","audio","","","","🔊"),
        ]
        with self._lock:
            for a in builtin:
                self._instances[a.id] = a
            if self._instances:
                self._current_id = list(self._instances.keys())[0]

    def load_config(self, path: str):
        p = Path(path)
        if not p.exists():
            self._load_builtin(); return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            with self._lock:
                self._instances.clear()
                for a in data.get("agents", []):
                    agent = AgentInstance(
                        id=a.get("id",""), name=a.get("name",""),
                        description=a.get("description",""), scene=a.get("scene","general"),
                        api_base=a.get("api_base",""), api_model=a.get("api_model",""),
                        api_key=a.get("api_key",""), icon=a.get("icon","🤖"),
                        config=a.get("config",{}),
                        llm_base=a.get("llm_base",""), llm_model=a.get("llm_model",""), llm_key=a.get("llm_key",""),
                    )
                    self._instances[agent.id] = agent
                cur = data.get("current_id")
                self._current_id = cur if cur and cur in self._instances else (list(self._instances.keys())[0] if self._instances else None)
                self._auto_failover = data.get("auto_failover", True)
                self._failover_timeout = data.get("failover_timeout", 30)
            logger.info("加载了 %d 个 Agent 实例", len(self._instances))
        except Exception as e:
            logger.error("加载配置失败: %s", e)
            self._load_builtin()

    @property
    def current_id(self) -> Optional[str]: return self._current_id
    @property
    def current(self) -> Optional[AgentInstance]:
        with self._lock:
            return self._instances.get(self._current_id) if self._current_id else None

    def get(self, agent_id: str) -> Optional[AgentInstance]:
        with self._lock: return self._instances.get(agent_id)
    def list_all(self) -> list[AgentInstance]:
        with self._lock: return list(self._instances.values())
    def add(self, agent: AgentInstance) -> bool:
        with self._lock:
            if agent.id in self._instances: return False
            self._instances[agent.id] = agent; return True
    def remove(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id not in self._instances: return False
            del self._instances[agent_id]
            if self._current_id == agent_id:
                self._current_id = next(iter(self._instances)) if self._instances else None
            return True
    def switch(self, agent_id: str) -> bool:
        with self._lock:
            if agent_id not in self._instances: return False
            self._current_id = agent_id; return True
    def switch_next_healthy(self) -> Optional[str]:
        if not self._auto_failover: return None
        with self._lock:
            ids = list(self._instances.keys())
            if not ids: return None
            idx = ids.index(self._current_id) if self._current_id in ids else 0
            for i in range(1, len(ids)):
                a = self._instances[ids[(idx+i)%len(ids)]]
                if a.status in (AgentStatus.ONLINE, AgentStatus.BUSY):
                    self._current_id = ids[(idx+i)%len(ids)]
                    logger.info("故障转移: %s → %s", ids[idx], self._current_id)
                    return self._current_id
            self._current_id = ids[0]
            logger.warning("所有 Agent 离线，退回 %s", ids[0])
            return ids[0]
    def record_success(self, agent_id: Optional[str] = None):
        aid = agent_id or self._current_id
        if aid and aid in self._instances: self._instances[aid].mark_success()
    def record_error(self, agent_id: Optional[str] = None):
        aid = agent_id or self._current_id
        if aid and aid in self._instances:
            self._instances[aid].mark_error()
            if self._auto_failover and self._instances[aid].error_count >= 3:
                new_id = self.switch_next_healthy()
                logger.warning("Agent %s 错误过多，切换到 %s", aid, new_id)

    def _start_health_checker(self):
        def loop():
            while True:
                time.sleep(self._health_check_interval)
                self._health_check()
        threading.Thread(target=loop, daemon=True).start()

    def _health_check(self):
        now = time.time()
        with self._lock:
            for a in self._instances.values():
                if a.last_heartbeat > 0 and (now - a.last_heartbeat) > self._failover_timeout:
                    if a.status != AgentStatus.OFFLINE:
                        logger.warning("Agent %s 心跳超时", a.id); a.mark_offline()
                if a.error_count > 5: a.mark_offline()

    # ==================== LLM 调用 ====================
    def _get_llm_config(self, agent: AgentInstance) -> dict:
        """获取 LLM 配置（优先 agent 自己的，其次全局的）。"""
        cfg = {
            "base": agent.llm_base or agent.api_base or _GLOB_LLM.get("base", ""),
            "model": agent.llm_model or agent.api_model or _GLOB_LLM.get("model", ""),
            "key": agent.llm_key or agent.api_key or _GLOB_LLM.get("key", ""),
        }
        return cfg

    def _call_llm(self, agent: AgentInstance, messages: list, temperature: float = 0.7, max_tokens: int = 2000) -> str:
        """调用 OpenAI 兼容的 LLM API。"""
        cfg = self._get_llm_config(agent)
        if not cfg["base"] or not cfg["key"]:
            return None

        url = cfg["base"].rstrip("/") + "/chat/completions"
        payload = {
            "model": cfg["model"] or "agnes-2.5-flash",
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(url, data=data, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", f"Bearer {cfg['key']}")

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                result = json.loads(resp.read().decode("utf-8"))
                return result["choices"][0]["message"]["content"]
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")
            logger.error("LLM API 错误 %d: %s", e.code, body[:200])
            return None
        except Exception as e:
            logger.error("LLM 调用失败: %s", e)
            return None

    def run_task(self, agent_id: Optional[str], task: str, max_steps: int = 10) -> dict:
        aid = agent_id or self._current_id
        if not aid or aid not in self._instances:
            return {"ok": False, "error": "没有可用的 Agent 实例", "agent_id": None}

        agent = self._instances[aid]
        agent.mark_busy()
        system_prompt = _SYSTEM_PROMPTS.get(agent.scene, "你是 BlueDeer 助手。")

        try:
            # 构建对话历史
            agent.history.append({"role": "user", "content": task})
            messages = [{"role": "system", "content": system_prompt}] + agent.history[-10:]  # 保留最近10轮

            # 尝试调用真实 LLM
            cfg = self._get_llm_config(agent)
            if cfg["base"] and cfg["key"] and cfg["model"]:
                result = self._call_llm(agent, messages)
                if result:
                    agent.history.append({"role": "assistant", "content": result})
                    return {
                        "ok": True, "agent_id": aid,
                        "output": result,
                        "model": cfg["model"],
                        "turn": len(agent.history) // 2,
                    }

            # LLM 不可用，返回场景提示
            if agent.scene in ("video","image","audio") and not cfg["base"]:
                return {
                    "ok": True, "agent_id": aid,
                    "output": f"⚠️ {agent.name} 尚未配置 LLM API。\n\n场景：{agent.scene_label()}\n提示：在 Agent 池配置中填写 api_base 和 api_key 后自动激活。\n当前全局配置：base={cfg['base'] or '未设置'} model={cfg['model'] or '未设置'}",
                }

            # 通用 fallback
            return {
                "ok": True, "agent_id": aid,
                "output": f"[{agent.name}] 已接收：{task}\n\n⚠️ LLM API 未配置或调用失败，当前为 Mock 模式。\n\n使用建议：\n1. 检查 agent/config.json 中是否有正确的 api_base 和 api_key\n2. 或在本 Agent 的 llm_base/llm_key 中单独配置\n\n可用场景：{agent.scene_label()}\n系统角色：{system_prompt[:50]}...",
            }
        except Exception as e:
            agent.mark_error()
            return {"ok": False, "agent_id": aid, "error": str(e)}
        finally:
            agent.mark_success()


# 全局单例
_pool: Optional[AgentPool] = None
_pool_lock = threading.Lock()

def get_pool() -> AgentPool:
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = AgentPool()
    return _pool

def reset_pool():
    global _pool
    with _pool_lock: _pool = None
