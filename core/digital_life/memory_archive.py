"""逝者记忆归档 MemoryArchive。

零基础读者可以这样理解：每只动物员工去世后，它的核心记忆、
生平摘要、遗言都会被存进一个"玻璃晶柜"（磁盘 JSON 文件）。
新入职的同种员工会去瞻仰前代的晶块，象征记忆的继承。

设计要点：
1. 纯 Python 标准库（json + os），零外部依赖
2. 原子写入（tmp + os.replace）保证断电不丢档
3. 按物种分文件存储：memory_archive/{species}.json
4. 每个物种文件是 list，按时间顺序存历代逝者
5. 线程安全（threading.RLock）
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any


class MemoryArchive:
    """逝者记忆归档（持久化到磁盘）。

    存储结构：
        {archive_dir}/{species}.json
        内容: [
            {
                "name": "鹿·忧郁",
                "species": "deer",
                "born_at": 1234567890,
                "died_at": 1234567999,
                "age_days": 12.5,
                "death_reason": "old_age",
                "death_zone_id": "deer",
                "gender": "female",
                "core_memory": [...],
                "life_summary": "..."
                "last_words": "..."
            },
            ...
        ]
    """

    __slots__ = ["_archive_dir", "_cache", "_lock", "_tag_index"]

    def __init__(self, archive_dir: str | None = None) -> None:
        """初始化归档目录。

        Args:
            archive_dir: 归档目录路径。None 时默认在
                         workspace/memory_archive/。
        """
        if archive_dir is None:
            archive_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                "memory_archive",
            )
        self._archive_dir = archive_dir
        self._lock = threading.RLock()
        self._cache: dict[str, list[dict]] = {}
        self._tag_index: dict[str, set[str]] = {}
        os.makedirs(self._archive_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # 写入
    # ------------------------------------------------------------------

    def archive_deceased(
        self,
        life_form: Any,
        life_summary: str = "",
        last_words: str = "",
    ) -> dict:
        """归档一个逝者。

        Args:
            life_form: 已故的 DigitalLifeForm 实例。
            life_summary: 生平摘要（由 Biosphere 调 LLM 生成）。
            last_words: 遗言（由 Biosphere 调 LLM 生成）。

        Returns:
            归档结果 dict，含 archive_id。
        """
        with self._lock:
            species = life_form.species
            # 提取核心记忆（深拷贝避免引用问题）
            core_memory = list(getattr(life_form, "core_memory", []))
            entry = {
                "name": life_form._name_obj,
                "species": species,
                "born_at": life_form.birth_time,
                "died_at": time.time(),
                "age_days": life_form.age,
                "death_reason": self._lookup_death_reason(life_form),
                "death_zone_id": getattr(life_form, "current_zone_id", ""),
                "gender": life_form.gender,
                "core_memory": core_memory,
                "life_summary": life_summary,
                "last_words": last_words,
            }
            # 读取已有列表
            entries = self._load_species(species)
            entries.append(entry)
            # 原子写入
            self._save_species(species, entries)
            # 更新缓存
            self._cache[species] = entries
            return {
                "ok": True,
                "archive_id": f"{species}_{len(entries) - 1}",
                "species": species,
                "entry_count": len(entries),
            }

    def _lookup_death_reason(self, life_form: Any) -> str:
        """从 environment.death_log 反查死因。"""
        env = getattr(life_form, "_environment", None)
        if env is None:
            return "unknown"
        try:
            for entry in reversed(env.death_log):
                if entry.get("name") == life_form._name_obj:
                    return entry.get("reason", "unknown")
        except Exception:
            pass
        return "unknown"

    # ------------------------------------------------------------------
    # 读取
    # ------------------------------------------------------------------

    def list_species(self) -> list[str]:
        """列出所有有归档的物种。"""
        with self._lock:
            result = []
            for fname in os.listdir(self._archive_dir):
                if fname.endswith(".json"):
                    result.append(fname[:-5])
            return sorted(result)

    def list_deceased(self, species: str) -> list[dict]:
        """列出某物种的所有逝者。"""
        with self._lock:
            return list(self._load_species(species))

    def get_deceased(self, species: str, index: int) -> dict | None:
        """获取某物种第 index 代逝者。"""
        with self._lock:
            entries = self._load_species(species)
            if 0 <= index < len(entries):
                return entries[index]
            return None

    def get_latest(self, species: str) -> dict | None:
        """获取某物种最近一位逝者。"""
        with self._lock:
            entries = self._load_species(species)
            return entries[-1] if entries else None

    def all_deceased(self) -> list[dict]:
        """所有物种的全部逝者（按死亡时间排序）。"""
        with self._lock:
            result = []
            for species in self.list_species():
                result.extend(self._load_species(species))
            result.sort(key=lambda x: x.get("died_at", 0))
            return result

    # ── 标签索引 ────────────────────────────────────────────────
    def add_tags_to_entry(self, species: str, index: int, tags: list[str]) -> bool:
        with self._lock:
            entries = self._load_species(species)
            if not (0 <= index < len(entries)):
                return False
            aid = f"{species}_{index}"
            entry_tags = entries[index].setdefault("tags", [])
            for t in tags:
                if t not in entry_tags:
                    entry_tags.append(t)
                self._tag_index.setdefault(t, set()).add(aid)
            self._save_species(species, entries)
            return True

    def search_by_tag(self, tag: str) -> list[dict]:
        with self._lock:
            aids = self._tag_index.get(tag, set())
            results = []
            for aid in aids:
                sp, idx = aid.rsplit("_", 1)
                idx = int(idx)
                entries = self._load_species(sp)
                if 0 <= idx < len(entries):
                    results.append(entries[idx])
            return results

    # ── 模糊搜索 ────────────────────────────────────────────────
    def fuzzy_search(self, query: str, threshold: float = 0.6) -> list[dict]:
        import difflib

        with self._lock:
            results = []
            for species, entries in self._cache.items():
                for i, e in enumerate(entries):
                    name = e.get("name", "")
                    summary = e.get("life_summary", "")
                    ratio = max(
                        difflib.SequenceMatcher(None, query, name).ratio(),
                        difflib.SequenceMatcher(None, query, summary).ratio(),
                    )
                    if ratio >= threshold:
                        results.append({**e, "_score": round(ratio, 3)})
            results.sort(key=lambda x: x["_score"], reverse=True)
            return results

    # ------------------------------------------------------------------
    # 持久化辅助
    # ------------------------------------------------------------------

    def _load_species(self, species: str) -> list[dict]:
        """从磁盘加载某物种的归档列表（带缓存）。"""
        if species in self._cache:
            return self._cache[species]
        path = self._path_of(species)
        if not os.path.exists(path):
            return []
        try:
            with open(path, "r", encoding="utf-8") as f:
                entries = json.load(f)
            if not isinstance(entries, list):
                entries = []
        except (json.JSONDecodeError, OSError):
            entries = []
        self._cache[species] = entries
        return entries

    def _save_species(self, species: str, entries: list[dict]) -> None:
        """原子写入某物种的归档列表。"""
        path = self._path_of(species)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(entries, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)

    def _path_of(self, species: str) -> str:
        """返回物种归档文件路径。"""
        return os.path.join(self._archive_dir, f"{species}.json")

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    def status(self) -> dict:
        """返回归档状态。"""
        with self._lock:
            species_list = self.list_species()
            total = 0
            per_species = {}
            for sp in species_list:
                count = len(self._load_species(sp))
                per_species[sp] = count
                total += count
            return {
                "archive_dir": self._archive_dir,
                "species_with_archive": len(species_list),
                "total_deceased": total,
                "per_species": per_species,
            }

    # ------------------------------------------------------------------
    # 测试辅助
    # ------------------------------------------------------------------

    def clear(self) -> None:
        """清空所有归档（仅测试用）。"""
        with self._lock:
            for sp in self.list_species():
                try:
                    os.remove(self._path_of(sp))
                except FileNotFoundError:
                    pass
            self._cache.clear()
