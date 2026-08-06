"""桌面宠物模式 + 系统托盘（commit 34）。

零基础读者可以这样理解：
- 用户点"桌面模式"按钮，浏览器变成 200×150 的小窗口，里面有一只小精灵在活动
- 后台每秒推送当前最活跃/最值得关注的那只智能体，前端小窗口渲染它的 sprite
- 紧急消息（如疾病、能量耗尽）通过浏览器原生 Notification 推送到桌面
- 可选的 Python 托盘程序（pystray）独立运行，双击打开管控台

零依赖：托盘部分若未装 pystray/Pillow 会自动降级为"无托盘"模式，不影响主流程。
"""

from __future__ import annotations

import datetime
import threading
import time

# ----------------------------------------------------------------------
# 桌面宠物状态管理（服务端推送当前活跃智能体）
# ----------------------------------------------------------------------


class DesktopPetState:
    """桌面宠物状态：决定小窗口显示哪只智能体。

    选择策略：
    - 优先级 1：正在生病/紧急状态的智能体（让用户立刻看到问题）
    - 优先级 2：刚发生大事件的智能体（任务完成、关系里程碑）
    - 优先级 3：当前最活跃的智能体（能量高、非睡眠）
    - 优先级 4：随机轮播
    """

    _instance: DesktopPetState | None = None
    _instance_lock = threading.Lock()

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._current_agent_id: str | None = None
        self._current_species: str = ""
        self._current_name: str = ""
        self._current_action_label: str = "idle"
        self._current_emotion: str = "contentment"
        self._current_emotion_intensity: float = 0.5
        self._health: float = 100.0
        self._energy: float = 80.0
        self._is_sick: bool = False
        self._disease_label: str = ""
        self._bubble_text: str = ""  # 桌面气泡
        self._bubble_expire: float = 0.0
        self._last_switch_ts: float = 0.0
        self._switch_interval: float = 60.0  # 默认 60 秒切换
        self._mode: str = "random"  # random / fixed:{agent_id}
        self._notification_pending: list[dict] = []  # 待推送的桌面通知
        self._enabled: bool = False  # 是否启用了桌面模式

    @classmethod
    def get_instance(cls) -> DesktopPetState:
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    # ---------------- 状态更新 ----------------

    def update_from_population(self, population: list) -> None:
        """从种群中选一只智能体作为桌面宠物展示。

        population: DigitalLifeForm 列表
        """
        if not population:
            return
        with self._lock:
            now = time.time()
            # 固定模式：不切换
            if self._mode.startswith("fixed:") and self._current_agent_id:
                # 找到当前固定的那只
                target_id = self._mode.split(":", 1)[1]
                for lf in population:
                    if not getattr(lf, "_alive", True):
                        continue
                    if self._get_lf_id(lf) == target_id:
                        self._sync_from_lf(lf)
                        return
                # 找不到 → 切回 random
                self._mode = "random"

            # random 模式：到时间切换
            should_switch = (
                self._current_agent_id is None
                or now - self._last_switch_ts > self._switch_interval
            )
            if should_switch:
                # 优先选有问题的（生病/能量低）
                candidates_sick = [
                    lf
                    for lf in population
                    if getattr(lf, "_alive", True)
                    and getattr(lf, "illness", None) is not None
                ]
                if candidates_sick:
                    import random

                    chosen = random.choice(candidates_sick)
                    self._sync_from_lf(chosen)
                    self._last_switch_ts = now
                    return
                # 其次选最近有大事件的（emotional_state 峰值）
                candidates_active = [
                    lf
                    for lf in population
                    if getattr(lf, "_alive", True)
                    and not getattr(lf, "sleeping", False)
                ]
                if candidates_active:
                    # 按 joy + contentment 排序
                    def _score(lf):
                        emo = getattr(lf, "emotional_state", {}) or {}
                        return emo.get("joy", 0) + emo.get("contentment", 0)

                    candidates_active.sort(key=_score, reverse=True)
                    chosen = candidates_active[0]
                    self._sync_from_lf(chosen)
                    self._last_switch_ts = now
                    return
            else:
                # 不切换，但同步当前智能体的最新状态
                if self._current_agent_id:
                    for lf in population:
                        if (
                            getattr(lf, "_alive", True)
                            and self._get_lf_id(lf) == self._current_agent_id
                        ):
                            self._sync_from_lf(lf)
                            return

    def _get_lf_id(self, lf) -> str:
        """构造智能体的稳定 ID（species + name）。"""
        return f"{getattr(lf, 'species', '?')}-{getattr(lf, '_name_obj', '?')}"

    def _sync_from_lf(self, lf) -> None:
        """从生命体同步状态到桌面宠物。"""
        emo = getattr(lf, "emotional_state", {}) or {}
        # 找主导情感
        max_k = "contentment"
        max_v = 0.0
        for k, v in emo.items():
            if v > max_v:
                max_v = v
                max_k = k
        illness = getattr(lf, "illness", None)
        # 动作标签
        action = getattr(lf, "current_action", None)
        action_label = "idle"
        if illness is not None:
            action_label = "sick"
        elif getattr(lf, "sleeping", False):
            action_label = "sleep"
        elif action is not None:
            try:
                action_label = action.value.lower()
            except AttributeError:
                action_label = str(action).lower()

        self._current_agent_id = self._get_lf_id(lf)
        self._current_species = getattr(lf, "species", "")
        self._current_name = getattr(lf, "_name_obj", "")
        self._current_action_label = action_label
        self._current_emotion = max_k
        self._current_emotion_intensity = max_v
        self._health = float(getattr(lf, "health", 100))
        self._energy = float(getattr(lf, "energy", 80))
        self._is_sick = illness is not None
        if illness is not None:
            self._disease_label = getattr(illness, "label", "生病")
        else:
            self._disease_label = ""

    # ---------------- 气泡 ----------------

    def show_bubble(self, text: str, duration: float = 4.0) -> None:
        """让桌面宠物头顶弹出一个气泡。"""
        with self._lock:
            self._bubble_text = text
            self._bubble_expire = time.time() + duration

    def get_current_bubble(self) -> str:
        with self._lock:
            if time.time() > self._bubble_expire:
                return ""
            return self._bubble_text

    # ---------------- 桌面通知 ----------------

    def push_notification(
        self, title: str, body: str, priority: str = "normal"
    ) -> None:
        """推一条桌面通知（前端会通过 SSE 收到并调用 Notification API）。"""
        with self._lock:
            self._notification_pending.append(
                {
                    "title": title,
                    "body": body,
                    "priority": priority,
                    "ts": time.time(),
                }
            )

    def pop_notifications(self) -> list[dict]:
        """取出所有待推送的通知（前端 SSE 拉取后清空）。"""
        with self._lock:
            notifs = list(self._notification_pending)
            self._notification_pending.clear()
            return notifs

    # ---------------- 模式控制 ----------------

    def set_mode(self, mode: str) -> None:
        """设置模式：random / fixed:{agent_id}"""
        with self._lock:
            self._mode = mode
            self._last_switch_ts = 0.0  # 强制下次切换

    def set_enabled(self, enabled: bool) -> None:
        with self._lock:
            self._enabled = bool(enabled)

    def is_enabled(self) -> bool:
        return self._enabled

    # ---------------- 快照 ----------------

    def snapshot(self) -> dict:
        """供前端小窗口渲染用。"""
        with self._lock:
            return {
                "enabled": self._enabled,
                "mode": self._mode,
                "agent_id": self._current_agent_id or "",
                "species": self._current_species,
                "name": self._current_name,
                "action": self._current_action_label,
                "emotion": self._current_emotion,
                "emotion_intensity": round(self._current_emotion_intensity, 2),
                "health": round(self._health, 1),
                "energy": round(self._energy, 1),
                "is_sick": self._is_sick,
                "disease_label": self._disease_label,
                "bubble": self.get_current_bubble(),
                "time": datetime.datetime.now().strftime("%H:%M:%S"),
            }


# ----------------------------------------------------------------------
# 模块级便捷函数
# ----------------------------------------------------------------------


def get_desktop_pet() -> DesktopPetState:
    return DesktopPetState.get_instance()


def update_desktop_pet(population: list) -> None:
    """每秒调用：从种群更新桌面宠物状态。"""
    get_desktop_pet().update_from_population(population)


def snapshot_desktop_pet() -> dict:
    return get_desktop_pet().snapshot()


def push_desktop_notification(title: str, body: str, priority: str = "normal") -> None:
    get_desktop_pet().push_notification(title, body, priority)


def pop_desktop_notifications() -> list[dict]:
    return get_desktop_pet().pop_notifications()


# ----------------------------------------------------------------------
# 可选：系统托盘（pystray + Pillow）
# ----------------------------------------------------------------------


def _try_make_pixel_antler_icon():
    """生成一个像素鹿角图标（16×16）。失败返回 None。"""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return None
    img = Image.new("RGBA", (16, 16), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # 简化的鹿角像素图（金色 #D4A574）
    gold = (212, 165, 116, 255)
    dark = (60, 50, 40, 255)
    # 鹿角
    for x, y in [
        (5, 2),
        (6, 2),
        (7, 2),
        (8, 2),
        (9, 2),
        (10, 2),
        (4, 3),
        (5, 3),
        (10, 3),
        (11, 3),
        (3, 4),
        (4, 4),
        (11, 4),
        (12, 4),
        (4, 5),
        (5, 5),
        (10, 5),
        (11, 5),
        (5, 6),
        (6, 6),
        (7, 6),
        (8, 6),
        (9, 6),
        (10, 6),
    ]:
        if 0 <= x < 16 and 0 <= y < 16:
            d.point((x, y), gold)
    # 头部
    for x, y in [
        (6, 8),
        (7, 8),
        (8, 8),
        (9, 8),
        (5, 9),
        (6, 9),
        (7, 9),
        (8, 9),
        (9, 9),
        (10, 9),
        (5, 10),
        (6, 10),
        (7, 10),
        (8, 10),
        (9, 10),
        (10, 10),
        (6, 11),
        (7, 11),
        (8, 11),
        (9, 11),
    ]:
        if 0 <= x < 16 and 0 <= y < 16:
            d.point((x, y), dark)
    # 眼睛
    d.point((6, 9), (255, 255, 255, 255))
    d.point((9, 9), (255, 255, 255, 255))
    return img


def run_tray_server(
    console_url: str = "http://127.0.0.1:8080/",
    stop_event: threading.Event | None = None,
) -> int:
    """启动系统托盘（阻塞调用）。

    Args:
        console_url: 双击托盘时打开的 URL
        stop_event: 外部停止信号
    Returns:
        0 成功退出，1 缺依赖，2 启动失败
    """
    try:
        import pystray
    except ImportError:
        logger.warning(
            "[tray] pystray 未安装，托盘功能不可用。安装：pip install pystray Pillow"
        )
        return 1
    icon_img = _try_make_pixel_antler_icon()
    if icon_img is None:
        logger.warning("[tray] Pillow 未安装或图标生成失败，托盘功能不可用。")
        return 1

    import webbrowser

    def _open_console():
        webbrowser.open(console_url)

    def _quit(icon, item):
        if stop_event is not None:
            stop_event.set()
        icon.stop()

    def _show_summary(icon, item):
        # 简单地打开管控台
        webbrowser.open(console_url)

    menu = pystray.Menu(
        pystray.MenuItem("打开管控台", _open_console, default=True),
        pystray.MenuItem("查看今日摘要", _show_summary),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("退出", _quit),
    )
    icon = pystray.Icon("BlueDeer", icon_img, "BlueDeer 森林公司 · 运行中", menu)
    try:
        icon.run()
        return 0
    except Exception as e:
        logger.error("[tray] 启动失败：%s", e)
        return 2


def start_tray_in_thread(
    console_url: str = "http://127.0.0.1:8080/",
    stop_event: threading.Event | None = None,
) -> threading.Thread | None:
    """在后台线程启动托盘。失败返回 None。"""
    try:
        import pystray  # noqa: F401
        from PIL import Image  # noqa: F401
    except ImportError:
        return None
    t = threading.Thread(
        target=run_tray_server,
        args=(console_url, stop_event),
        daemon=True,
        name="desktop-tray",
    )
    t.start()
    return t
