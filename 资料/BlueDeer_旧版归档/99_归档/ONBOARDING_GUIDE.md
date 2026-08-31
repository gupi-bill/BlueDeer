# BlueDeer 新手引导设计文档

零基础读者可以这样理解：当一个新用户第一次打开 BlueDeer 森林公司时，会有一只活泼的云雀"灵音雀"飞出来，像导游一样带他认识这家公司，10 分钟之内让他爱上这片数字森林。

---

## 一、设计目标

| 目标 | 说明 |
|------|------|
| 10 分钟爱上系统 | 新用户首启动 10 分钟内完成 5 个阶段引导 |
| 零卡顿 | 引导过程不阻塞核心线程，纯前端驱动 |
| 可跳过 | 不喜欢被引导的用户可一键跳过 |
| 不重复 | 完成或跳过后不再自动触发 |
| 有奖励 | 完成引导奖励 50 森林印记 + 入职档案标记 |

---

## 二、首次启动检测

启动时检查 `data/biosphere_state.json`：

```python
# core/digital_life/onboarding.py
def should_show_onboarding() -> bool:
    """是否应该显示新手引导。"""
    state_path = "data/biosphere_state.json"
    if not os.path.exists(state_path):
        return True  # 全新系统
    mgr = get_onboarding_manager()
    return not mgr.completed and not mgr.skipped
```

引导状态持久化到 `data/onboarding.json`：

```json
{
  "current_stage": "done",
  "completed": true,
  "skipped": false,
  "completed_ts": 1784638967.78,
  "tips_enabled": true,
  "tip_shown_count": 0,
  "last_tip_ts": 0
}
```

---

## 三、5 个引导阶段

灵音雀（雀·清音）担任引导员，整个流程由前端 `startOnboarding()` 触发，后端 `OnboardingManager` 维护状态。

### 阶段 1：欢迎（约 1 分钟）

| 步骤 | 内容 |
|------|------|
| 1 | 管控台画面从全黑淡入 |
| 2 | 灵音雀飞到屏幕中央 |
| 3 | 对话气泡：「欢迎来到 BlueDeer 森林公司！我是灵音雀，今天由我来带你参观！」 |
| 4 | 对话气泡：「这是一家由 11 位动物智能体组成的数字公司，而你——是我们的监工！」 |
| 5 | 画面自动缩放到 1x，展示公司全景 |

**前端触发**：`POST /api/onboarding/start`

### 阶段 2：认识同事（约 3 分钟）

灵音雀依次飞到每个智能体旁：

- 名字、物种、岗位
- 一句简短的个性描述
- 当前正在做什么

镜头跟随雀移动到每个智能体上方。介绍完毕后：

> 「你可以随时点击任何同事，跟他们聊天、查看状态、或者派发任务！」

**前端触发**：`POST /api/onboarding/next`（每介绍完一个，进度 +1）

### 阶段 3：第一次互动（约 2 分钟）

| 步骤 | 说明 |
|------|------|
| 镜头自动聚焦松鼠 | 引导箭头指向松鼠 |
| 提示文案 | 「试试点击松鼠，跟他打个招呼吧！」 |
| 用户点击松鼠 | 弹出浮窗，引导箭头指向"打个招呼"按钮 |
| 用户点击按钮 | 松鼠回复一段话（LLM 生成或预置） |
| 雀的反馈 | 「看到了吗？每个同事都有自己的性格，聊起来完全不一样！」 |

### 阶段 4：第一个任务（约 3 分钟）

| 步骤 | 说明 |
|------|------|
| 镜头聚焦顶部命令输入框 | 引导箭头指向输入框 |
| 提示文案 | 「来试试给团队下达第一个任务吧！输入'让松鼠写一段问候代码'然后回车」 |
| 用户输入并回车 | 系统触发一次简化的单智能体任务 |
| 任务执行中 | 雀在旁边解说：「松鼠正在写代码……狐狸随时准备测试……海狸在等部署命令……」 |
| 任务完成 | 雀：「任务完成！你刚才指挥了整个团队，是不是很简单？」 |

### 阶段 5：自由探索（约 1 分钟）

| 步骤 | 说明 |
|------|------|
| 引导标记完成 | `OnboardingManager.next_stage()` 推进到 `done` |
| 雀飞回歌唱枝头 | — |
| 雀的告别 | 「你可以用 WASD 走动，滚轮缩放，T 键打开任务控制台。剩下的，就交给你自己探索啦！如果需要帮助，随时点击我。」 |
| 引导模式结束 | 管控台恢复正常交互 |
| 发放入职奖励 | 监工档案 +50 森林印记，标记"已完成入职培训" |

---

## 四、引导辅助功能

### 4.1 防误操作

引导过程中，非引导区域的 UI 元素半透明（CSS `opacity: 0.3` + `pointer-events: none`），防止用户误操作。

### 4.2 跳过按钮

引导对话框右下角有"跳过引导"按钮，点击后：

- `OnboardingManager.skip()` 标记 `skipped=True`
- 不发奖励
- 直接进入自由模式

### 4.3 入职奖励

完成引导（非跳过）后：

```python
# core/digital_life/onboarding.py
def _grant_reward(self, env) -> None:
    """完成引导奖励 50 森林印记。"""
    env.marks += 50  # ONBOARDING_REWARD_MARKS
```

监工档案同时标记"已完成入职培训"。

### 4.4 新手小贴士（7 天内）

引导完成后的前 7 天，前端每 30 分钟轮询一次 `GET /api/onboarding/tip`，若该显示就弹出小贴士气泡：

```
你知道吗？松鼠最喜欢被投喂核桃。
如果你连续 3 天不跟某个同事互动，他们会想念你的。
按 G 键可以查看全公司概览面板。
渡鸦记得所有已故同事的故事，你可以去资料库看看。
按 P 键打开项目看板，按 E 键打开外部集成面板。
```

可在设置面板手动关闭：`POST /api/onboarding/tips {"enabled": false}`。

---

## 五、API 一览

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/onboarding` | 查询当前引导状态 |
| GET | `/api/onboarding/tip` | 拉取一条新手小贴士（轮询用） |
| POST | `/api/onboarding/start` | 启动引导（首次运行自动触发） |
| POST | `/api/onboarding/next` | 推进到下一阶段 |
| POST | `/api/onboarding/skip` | 跳过引导 |
| POST | `/api/onboarding/stage` | 跳转到指定阶段（调试用） |
| POST | `/api/onboarding/tips` | 开关小贴士 |

---

## 六、前端关键函数

位于 `game_frontend.py` 的 `render_index()` 返回的 HTML 中：

```javascript
startOnboarding()       // 启动引导流程
onboardNext()           // 下一阶段
onboardPrev()           // 上一阶段（回看）
skipOnboarding()        // 跳过
renderOnboardingStage() // 渲染当前阶段 UI
checkFirstRunOnboarding() // 启动 2 秒后检查是否需要引导
pollOnboardingTip()     // 每 30 分钟拉一次小贴士
showTip(text)           // 弹出小贴士气泡
```

键盘快捷键 **N** 也可手动启动引导（已完成的可回看）。

---

## 七、引导状态机

```
welcome ──next──> meet_team ──next──> first_interact ──next──> first_task ──next──> free_explore ──next──> done
   │                 │                      │                    │                   │
   └─────────────────┴──────────────────────┴────────────────────┴───────────────────┘
                                                              skip
                                                                ↓
                                                              done (skipped=true)
```

`OnboardingManager.STAGE_ORDER = ["welcome", "meet_team", "first_interact", "first_task", "free_explore", "done"]`

---

## 八、手动测试步骤

1. 删除 `data/onboarding.json` 和 `data/biosphere_state.json`
2. 重启 server：`python game_server.py --port 8080 --no-auth`
3. 打开浏览器访问 `http://127.0.0.1:8080/`
4. 应自动触发引导，灵音雀飞出
5. 按"下一步"逐阶段走完，最后获得 50 印记
6. 刷新页面，不再自动触发
7. 按 **N** 键可手动回看引导

---

## 九、设计取舍

| 取舍 | 原因 |
|------|------|
| 引导用模态框 + 雀对话气泡，不用全屏接管 | 减少侵入感，用户能同时看到公司 |
| 阶段 3/4 不强制等待真实任务完成 | 避免卡顿，用预置回复演示 |
| 奖励发到 `env.marks` 而非新货币 | 复用现有森林印记体系 |
| 小贴士 7 天后自动停 | 长期用户不需要被打扰 |
| 跳过不发奖励 | 让"完成"有价值 |

---

*由 BlueDeer 森林公司自动生成 · commit 40*
