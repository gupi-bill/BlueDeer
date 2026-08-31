/* Odysseus 深度汉化（仅 UI，绝不碰聊天内容/AI 回复）
 * 安全策略：
 *  - 遍历 document.body 的纯文本节点，做「整节点精确匹配」翻译；
 *  - 翻译 title / placeholder / aria-label 等属性；
 *  - 严格跳过聊天、输入框、代码、Markdown 渲染容器（SKIP）；
 *  - 常驻 MutationObserver 仅处理「非聊天容器」里新增的节点（动态弹窗也覆盖）；
 *  - 流式 AI 回复命中 SKIP，永不污染。
 * 专有名词/产品名/URL/API 路径/颜色值/参数技术名保留英文。
 */
(function () {
  'use strict';

  // ---- 严格跳过的容器（聊天、输入、代码、Markdown）----
  var SKIP = [
    '#chat-messages', '.chat-messages', '.message', '.message-content',
    '.markdown-body', '.composer-textarea', '#message', '#chat-input',
    '.chat-input', '.prompt-input', 'textarea', 'input',
    '[contenteditable="true"]', '[contenteditable]', 'pre', 'code',
    '.msg', '.ai-message', '.user-message', '.streaming', '.reasoning',
    '.thinking', '.cm-editor', '.CodeMirror', '.hljs', '.token',
    '.monaco-editor', '.prose', '.md', '.rendered-markdown'
  ].join(',');

  // ---- 完整中英字典（UI 文案，整节点精确匹配）----
  var DICT = {
    // 导航 / 主区域
    'New Chat': '新建对话', 'New chat': '新建对话', 'Chats': '对话', 'Chat': '对话',
    'Chat Area': '对话区', 'Chat Bar': '对话栏', 'Chat Bubbles': '对话气泡',
    'Chat Input / Prompt Area': '对话输入/提示区', 'Chat history list': '对话历史列表',
    'Calendar': '日历', 'Cookbook': '模型食谱', 'Deep Research': '深度调研',
    'Gallery': '图库', 'Library': '资料库', 'Notes': '笔记', 'Tasks': '任务',
    'Brain': '记忆', 'Tools': '工具', 'Email': '邮件', 'Theme': '主题',
    'Themes': '主题', 'Settings': '设置', 'Search': '搜索', 'Compare': '对比',
    'Documents': '文档', 'Document Editor': '文档编辑器', 'Skills': '技能',
    'Admin': '管理', 'Agent': '智能体', 'Agent / Chat': '智能体/对话',
    'Agent Tools': '智能体工具', 'Built-in Tools': '内置工具', 'Model': '模型',
    'Model Defaults': '模型默认', 'Default Chat Model': '默认对话模型',
    'Memory': '记忆', 'Memories': '记忆', 'Persona': '人格', 'Personas': '人格',
    'Workspace': '工作区', 'Sidebar': '侧边栏', 'Panel': '面板', 'Mode': '模式',
    'Mode switcher': '模式切换', 'Controls': '控制项', 'Providers': '供应商',
    'Provider': '供应商', 'Endpoint': '端点', 'Endpoints': '端点',
    'Integration': '集成', 'Integrations': '集成', 'Account': '账户',
    'User': '用户', 'Users': '用户', 'Local (Kokoro-82M)': '本地 (Kokoro-82M)',
    'API (direct)': 'API（直连）', 'API Key': 'API 密钥',
    'Add': '添加', 'Add API Models': '添加 API 模型', 'Add Integration': '添加集成',
    'Add Local Models': '添加本地模型', 'Add Memory': '添加记忆',
    'Add Models': '添加模型', 'Add Ollama': '添加 Ollama', 'Add Skill': '添加技能',
    'Add User': '添加用户', 'Added Models': '已添加模型',
    'Add a local model server (Ollama, llama.cpp, vLLM).': '添加本地模型服务（Ollama、llama.cpp、vLLM）。',
    'Add a memory': '添加一条记忆',
    'Add, edit, delete, and test accounts in Integrations.': '在集成中添加、编辑、删除并测试账户。',
    'All skills': '全部技能', 'Allow anyone to create an account from the login page': '允许任何人在登录页创建账户',
    'All Levels': '全部等级', 'All external service connections in one place.': '所有外部服务连接集中管理。',
    'All eight categories above, in one go. Same effect as wiping each one in sequence.': '一次性清空以上全部八类，效果等同于依次分别清空。',
    'Analyze images with a vision-capable model.': '使用支持视觉的模型分析图片。',
    'Appearance': '外观', 'Apply': '应用', 'Approve': '批准',
    'Attach Files': '附加文件', 'Attach files': '附加文件', 'Audit': '审计',
    'Audit all publishes passing, necessary skills at or above this confidence. Off = keep audit results as drafts unless manually approved.': '审计会发布达到该置信度的必要技能。关闭则审计结果保留为草稿，除非手动批准。',
    'Auto reply, newsletter unsubscribe, and writing style live in the Email window.': '自动回复、退订与写作风格位于邮件窗口。',
    'Auto-approve skills': '自动批准技能', 'Auto-detect': '自动检测',
    'Auto-extract memories': '自动提取记忆', 'Auto-extract skills': '自动提取技能',
    'Auto-poll': '自动轮询', 'Automatically draft reusable skills from your workflows. Audit all can publish passing skills using the threshold below.': '从你的工作流自动起草可复用技能。审计可发布达到以下阈值的技能。',
    'Automatically extract memories from conversations.': '从对话中自动提取记忆。',
    'Avatar & name': '头像与名称', 'Background': '背景', 'Background / Effect': '背景/特效',
    'Balanced': '均衡', 'Blur emails, tokens, and secrets in AI output': '在 AI 输出中模糊化邮件、令牌与密钥',
    'Border': '边框', 'Border Chat Bubble': '边框对话气泡', 'Brand name': '品牌名称',
    'Browser (built-in)': '浏览器（内置）', 'Browser notification (default)': '浏览器通知（默认）',
    'By Folder': '按文件夹', 'Calendar settings': '日历设置', 'Cancel': '取消',
    'Change Password': '修改密码', 'Change the session name': '修改会话名称',
    'Channel': '频道', 'ChatGPT Subscription': 'ChatGPT 订阅',
    'Clear Advanced Overrides': '清除高级覆盖', 'Clear offline': '清除离线',
    'Clears `memory.json`, the Memory table, and the vector store. Skills not affected.': '清除 memory.json、记忆表与向量库，不影响技能。',
    'Click a shortcut to rebind. Press Escape to cancel.': '点击快捷键重新绑定，按 Esc 取消。',
    'Code Bg': '代码背景', 'Code Blocks': '代码块', 'Code Text': '代码文字',
    'Color Harmony': '色彩调和', 'Colors': '颜色', 'Comfortable': '舒适',
    'Compact': '紧凑', 'Complementary': '互补色', 'Confidence': '置信度',
    'Configure TTS provider for assistant message read-aloud.': '配置 TTS 供应商以朗读助手消息。',
    'Configure email account, ntfy server, etc. in': '在以下配置邮件账户、ntfy 服务器等：',
    'Configure which model to use for image generation.': '配置用于图像生成的模型。',
    'Connect a cloud provider (OpenAI, Anthropic, DeepSeek, OpenRouter, etc.).': '连接云供应商（OpenAI、Anthropic、DeepSeek、OpenRouter 等）。',
    'Connection mode': '连接模式', 'Constellations': '星座',
    'Controls for the agent tool loop.': '智能体工具循环的控制项。',
    'Controls how fired note reminders are delivered.': '控制笔记提醒的发送方式。',
    'Controls how many relevant published or approved skills are added to each agent request.': '控制每次智能体请求注入多少相关技能。',
    'Copy Chat': '复制对话', 'Creative': '创意', 'Custom': '自定义',
    'Custom Fonts': '自定义字体', 'Custom URL': '自定义 URL', 'Customize': '自定义',
    'Danger Zone': '危险区', 'Dark': '深色', 'Data Backup': '数据备份',
    'DEBUG': '调试', 'Default': '默认', 'Default (warm, neutral)': '默认（温暖、中性）',
    'Default Themes': '默认主题', 'Delete': '删除', 'Delete All': '全部删除',
    'Delete Chat': '删除对话', 'Delete all calendar': '删除全部日历',
    'Delete all chats': '删除全部对话', 'Delete all documents': '删除全部文档',
    'Delete all gallery': '删除全部图库', 'Delete all memory': '删除全部记忆',
    'Delete all notes': '删除全部笔记', 'Delete all skills': '删除全部技能',
    'Delete all tasks': '删除全部任务', 'Delete everything': '删除所有内容',
    'Delete non passing': '删除未通过的', 'Density': '密度', 'Disabled': '已禁用',
    'Dots': '圆点', 'Drafts only': '仅草稿', 'Drop': '拖放',
    'Drops `data/skills/` (all SKILL.md files). Memory not affected.': '删除 data/skills/（所有 SKILL.md 文件），不影响记忆。',
    'DuckDuckGo (free, no key)': 'DuckDuckGo（免费，无需密钥）',
    'Edit persona settings here →': '在此编辑人格设置 →',
    'Email Accounts': '邮件账户', 'Email Settings': '邮件设置', 'Email Tasks': '邮件任务',
    'Embers': '余烬', 'Enable or disable tools available to the AI agent.': '启用或禁用 AI 智能体可用的工具。',
    'Endpoints you\'ve connected. Probe re-tests them all; Clear offline removes the dead ones.': '已连接的端点。探测会重新测试全部；清除离线会移除失效的。',
    'Every document and version. Drafts, exports, library — all gone.': '每个文档及其版本，草稿、导出、资料库——全部清空。',
    'Every event and every calendar (incl. CalDAV-synced ones; resync to restore).': '每个事件与每个日历（含 CalDAV 同步的；重新同步可恢复）。',
    'Every image record and the upload directory on disk.': '每条图片记录及磁盘上的上传目录。',
    'Every note, todo, and checklist.': '每条笔记、待办与清单。',
    'Every scheduled task and its run history (Tasks tool).': '每个定时任务及其运行历史（任务工具）。',
    'Every session, message, and chat history. Documents/notes/etc. stay.': '每个会话、消息与对话历史。文档/笔记等保留。',
    'Export': '导出', 'Export Data': '导出数据',
    'Export or import your user data (memories, presets, settings, skills, preferences) as a JSON file.': '将用户数据（记忆、预设、设置、技能、偏好）导出或导入为 JSON 文件。',
    'Extract Parallel': '并行提取数', 'Extract Timeout': '提取超时',
    'Extract from Sent (15 emails)': '从已发送提取（15 封邮件）',
    'Extract memories from this session': '从本会话提取记忆', 'Fable': '寓言',
    'Fallbacks': '备选', 'Font': '字体', 'Font & Layout': '字体与布局',
    'Frosted': '磨砂', 'Full-width chat': '全宽对话', 'Generate': '生成',
    'Google Gemini': 'Google Gemini', 'Google PSE': 'Google PSE', 'Groq': 'Groq',
    'Group': '群组', 'Harmony': '调和', 'High (best quality)': '高（最佳质量）',
    'How': '如何', 'How you\'re reminded': '你如何被提醒', 'Image': '图片',
    'Image Generation': '图像生成', 'Import': '导入', 'Import Data': '导入数据',
    'Import URL': '导入 URL', 'Import a skill from GitHub or': '从 GitHub 导入技能，或',
    'Incognito Mode': '隐身模式', 'Initializing logs terminal viewer...': '正在初始化日志终端查看器…',
    'Inject': '注入', 'Inject Skills': '注入技能', 'Input Bg': '输入框背景',
    'Input Border': '输入框边框', 'Integration': '集成', 'Integrations': '集成',
    'Intensity': '强度', 'Irreversible. Each wipe targets one category — pick exactly what you want gone.': '不可逆。每次清除针对一类——精确选择要删除的内容。',
    'Keyboard Shortcuts': '键盘快捷键', 'LLM': 'LLM', 'Larger': '更大',
    'Last Active': '最近活跃', 'Library': '资料库', 'Light': '浅色',
    'Live diagnostic logs and system output from the Odysseus process.': '来自 Odysseus 进程的实时诊断日志与系统输出。',
    'Loading...': '加载中…', 'Logo & tips on empty chat': '空对话时的 logo 与提示',
    'Long-term facts the AI remembers across chats — recall, edit, or curate.': 'AI 跨对话记住的长期事实——可回顾、编辑或整理。',
    'Low (fastest, cheapest)': '低（最快、最省）', 'Manage email background tasks in Tasks.': '在任务中管理邮件后台任务。',
    'Max Tokens': '最大令牌', 'Max skills per request': '每次请求最大技能数',
    'Max steps per message': '每条消息最大步数', 'Medium (default)': '中（默认）',
    'Minimum confidence': '最小置信度', 'Mistral': 'Mistral', 'Mode': '模式',
    'Mode switcher': '模式切换', 'Model Defaults': '模型默认',
    'Model name & export above chat': '模型名称并在对话上方导出',
    'Model used for Deep Research, more settings under': '用于深度调研的模型，更多设置在',
    'Monochromatic': '单色', 'Monospace': '等宽', 'More Tools': '更多工具',
    'Most used': '最常用', 'NVIDIA': 'NVIDIA', 'Name': '名称',
    'New chat ready.': '新对话已就绪。', 'Newest': '最新', 'Newest First': '最新优先',
    'No API endpoints yet.': '还没有 API 端点。', 'No limit': '无限制',
    'No local endpoints yet.': '还没有本地端点。', 'No memory, no history saved': '不保存记忆与历史',
    'Nobody': '隐身', 'Notes': '笔记', 'Nova': 'Nova', 'Odysseus': 'Odysseus',
    'Odysseus Chat': 'Odysseus 对话', 'Odysseus Logo': 'Odysseus 徽标', 'Oldest': '最早',
    'Ollama Cloud': 'Ollama Cloud', 'Onyx': 'Onyx', 'Open Email Settings': '打开邮件设置',
    'Open Integrations': '打开集成', 'Open Tasks': '打开任务', 'Open signup': '开放注册',
    'OpenAI': 'OpenAI', 'OpenCode Go': 'OpenCode Go', 'OpenCode Zen': 'OpenCode Zen',
    'OpenDyslexic (dyslexia-friendly)': 'OpenDyslexic（阅读障碍友好）', 'OpenRouter': 'OpenRouter',
    'Or create a skill by hand — title, what it solves, and an approach.': '或手动创建技能——标题、解决的问题与方案。',
    'Overflow menu': '溢出菜单', 'PDF': 'PDF', 'Panel': '面板', 'Payload': '载荷',
    'Peek': '预览', 'Perlin Flow': '柏林流', 'Persona': '人格',
    'Persona picker & system prompt': '人格选择器与系统提示', 'Personas': '人格',
    'Petals': '花瓣', 'Plan mode': '计划模式', 'Precise / Code': '精准/代码',
    'Prefix': '前缀', 'Preview': '预览', 'Prompt': '提示', 'Provider': '供应商',
    'Proxy': '代理', 'Public App URL': '公开应用 URL', 'Published only': '仅已发布',
    'Quality': '质量', 'RAG': '知识库检索', 'Rain': '雨', 'Recent': '最近',
    'Registration': '注册', 'Reminders': '提醒',
    'Remove this session permanently': '永久删除此会话', 'Rename': '重命名',
    'Rename Session': '重命名会话', 'Research': '调研', 'Research Model': '调研模型',
    'Reset to Default': '重置为默认', 'Results per query': '每次查询结果数',
    'Reusable procedures the AI can call via /skill — sort by confidence to surface the proven ones.': 'AI 可通过 /skill 调用的可复用流程——按置信度排序以凸显可靠的。',
    'Runs background tasks (compaction, cleanup, auto-naming, retrieving memories from files) on a small/local model instead of your chat model. Leave blank to use the chat model.': '在小型/本地模型而非对话模型上运行后台任务（压缩、清理、自动命名、从文件检索记忆）。留空则使用对话模型。',
    'Sage': '贤者', 'Same as chat': '同对话', 'Same as web search': '同联网搜索',
    'Sans-serif': '无衬线', 'Save': '保存', 'Save / Share': '保存/分享',
    'Save to Documents': '保存到文档', 'SearXNG': 'SearXNG',
    'SearXNG (self-hosted)': 'SearXNG（自托管）', 'Search': '搜索',
    'Search API used for web search and deep research.': '用于联网搜索与深度调研的搜索 API。',
    'Search →': '搜索 →', 'Select': '选择', 'Select model': '选择模型',
    'Select persona...': '选择人格…', 'Send Btn': '发送按钮', 'Send Hover': '发送悬停',
    'Send from': '发送自', 'Send to': '发送至', 'Sensitive Blur': '敏感模糊',
    'Sequential': '顺序', 'Serif': '衬线', 'Serper': 'Serper', 'Serper.dev': 'Serper.dev',
    'Session Header': '会话头部', 'Session Name': '会话名称',
    'Set to 0 to disable skill injection.': '设为 0 以关闭技能注入。', 'Settings': '设置',
    'Settings Button': '设置按钮', 'Share defaults with users': '与用户共享默认',
    'Shell': '终端', 'Shimmer': '微光', 'Shortcuts': '快捷键',
    'Show <think> collapsible bars': '显示 <think> 可折叠条', 'Sidebar': '侧边栏',
    'Size': '大小', 'Skills': '技能', 'Solid': '实心', 'Sorting...': '排序中…',
    'Spacious': '宽松', 'Sparkles': '火花', 'Speed': '速度', 'Start': '开始',
    'Strip emojis from AI replies': '从 AI 回复中去除表情符号', 'Suffix': '后缀',
    'Synapse': '突触', 'System': '系统', 'System prompt': '系统提示',
    'TTS Mode': 'TTS 模式', 'Tags': '标签', 'Tasks': '任务', 'Tavily': 'Tavily',
    'Temperature': '温度', 'Test': '测试', 'Text': '文本', 'Text size': '文字大小',
    'Text to Speech': '文字转语音', 'Text-only Emojis': '仅文本表情',
    'The library can grow; cleanup retires weak/duplicate skills only after review.': '资料库可增长；清理仅在审核后退役薄弱/重复技能。',
    'The model used when creating a new chat session.': '创建新对话会话时使用的模型。',
    'Theme': '主题', 'Themes': '主题', 'Thinking Process': '思考过程', 'Tidy': '整理',
    'Timeout': '超时', 'Title': '标题', 'Together AI': 'Together AI',
    'Toggle On': '开启', 'Tool call limit': '工具调用上限', 'Tools': '工具',
    'Triadic': '三分色', 'Two-Factor Authentication': '双因素认证', 'URL': 'URL',
    'Update Password': '更新密码', 'Use the full window width (desktop)': '使用全窗口宽度（桌面）',
    'Used to build clickable links back to Odysseus inside outgoing reminder / urgent-email emails (e.g.': '用于在发出的提醒/紧急邮件中构建可点击的回链（例如',
    'Used when AI drafts email replies. Keep this email-specific: greetings, sign-off, tone, and length.': 'AI 起草邮件回复时使用。保持邮件专属：问候、落款、语气与长度。',
    'User': '用户', 'User Chat Bubble': '用户对话气泡', 'Users': '用户',
    'Utility Model': '工具模型', 'Vision': '视觉', 'Voice': '语音',
    'Web Search': '联网搜索', 'Webhook': 'Webhook', 'Welcome Message': '欢迎语',
    'When on, the utility model writes a short, warm one-line reminder for browser, email, ntfy, and webhook reminders instead of just the raw note content.': '开启后，工具模型为浏览器、邮件、ntfy 与 webhook 提醒写一句简短温暖的提醒，而非仅原始笔记内容。',
    'When on, users without a personal default inherit the global default model (only if those models are allowed for them).': '开启后，无个人默认的用户继承全局默认模型（仅限其被允许的模型）。',
    'When to use': '使用时机', 'Whole section (header + all tools)': '整个分区（头部+全部工具）',
    'Workspace': '工作区', 'Writing Style': '写作风格', 'Your Themes': '你的主题',
    'Z.AI (Zhipu)': 'Z.AI（智谱）', 'Z.AI Coding Plan': 'Z.AI 编程方案',
    'manage': '管理', 'new': '新建', 'all': '全部', 'All': '全部',

    // JS 动态 UI 文案
    'AI is processing': 'AI 处理中',
    'AI tidy: delete junk sessions and organize into folders': 'AI 整理：删除垃圾会话并归入文件夹',
    'Active - click to pause': '运行中 - 点击暂停',
    'Active email for all email settings': '所有邮件设置的活跃邮箱',
    'Add a tag': '添加标签', 'Add a to-do…': '添加待办…',
    'Add checkmark (then click on PDF)': '添加对勾（然后点击 PDF）',
    'Add details': '添加详情', 'Add model directory': '添加模型目录',
    'Add server': '添加服务器', 'Add signature (then click on PDF)': '添加签名（然后点击 PDF）',
    'Add text box (then click on PDF)': '添加文本框（然后点击 PDF）',
    'Add text — click to cycle size': '添加文字 — 点击切换大小',
    'Also create a calendar event on the Cookbook calendar': '同时在模型食谱日历创建事件',
    'Audit now': '立即审计', 'Calendar settings': '日历设置',
    'Cancel (Esc)': '取消（Esc）', 'Cancel event': '取消事件', 'Cancelled by user': '用户已取消',
    'Change date': '更改日期', 'Change time': '更改时间', 'Clear AI tags': '清除 AI 标签',
    'Clear Server': '清除服务器', 'Clear album filter': '清除相册筛选',
    'Clear all selections': '清除全部选择', 'Clear filter': '清除筛选',
    'Clear finished tasks': '清除已完成任务', 'Clear manual hardware': '清除手动硬件',
    'Click to copy': '点击复制', 'Click to edit': '点击编辑',
    'Click to fill in chat': '点击填入对话', 'Click to rename': '点击重命名',
    'Close all suggestions': '关闭全部建议', 'Close edit': '关闭编辑',
    'Close email': '关闭邮件', 'Close this configuration panel': '关闭此配置面板',
    'Collapse AI edit': '折叠 AI 编辑', 'Collapse panel': '折叠面板',
    'Compare changes': '对比更改', 'Configure & serve': '配置并服务',
    'Connect with Google': '用 Google 连接', 'Copy Chat': '复制对话', 'Copy URL': '复制 URL',
    'Copy all items': '复制全部项', 'Copy command to clipboard': '复制命令到剪贴板',
    'Copy email': '复制邮件', 'Copy launch command': '复制启动命令', 'Copy log': '复制日志',
    'Copy setup': '复制配置', 'Copy the run output + verdict': '复制运行输出与判定',
    'Copy this log entry': '复制此日志项', 'Copy token': '复制令牌',
    'Create Persistent Chat': '创建常驻对话', 'Create event': '创建事件',
    'Create event in calendar': '在日历创建事件', 'Create new blank document': '创建新空白文档',
    'Currently showing this album — click X to clear': '当前显示此相册 — 点击 X 清除',
    'Default server': '默认服务器', 'Delete calendar': '删除日历', 'Delete forever': '永久删除',
    'Delete item': '删除项', 'Delete permanently': '永久删除', 'Delete project': '删除项目',
    'Delete reminders whose time has passed': '删除已过期的提醒',
    'Delete selected': '删除所选', 'Delete theme': '删除主题', 'Delete this server': '删除此服务器',
    'Discard this new server': '丢弃此新服务器', 'Document actions': '文档操作',
    'Document content...': '文档内容…', 'Download JSON': '下载 JSON',
    'Download all attachments': '下载全部附件', 'Download complete': '下载完成',
    'Download destination': '下载位置',
    'Draft a reply with AI (fast + optional context)': '用 AI 起草回复（快 + 可选上下文）',
    'Draft a task with AI': '用 AI 起草任务', 'Draft reply': '起草回复',
    'Edit & relaunch': '编辑并重启动', 'Edit (E)': '编辑（E）', 'Edit / relaunch': '编辑/重启动',
    'Edit code': '编辑代码', 'Edit in Settings': '在设置中编辑', 'Edit item': '编辑项',
    'Edit or preview': '编辑或预览', 'Edit photo': '编辑图片', 'Edit reminder': '编辑提醒',
    'Edit serve': '编辑服务', 'Edit source (Ctrl+Alt+M to toggle)': '编辑源码（Ctrl+Alt+M 切换）',
    'Email (IMAP/SMTP)': '邮件（IMAP/SMTP）', 'Email settings': '邮件设置',
    'Enable this check-in': '启用此签到', 'Enter password to disable': '输入密码以禁用',
    'Esc cancels select mode': 'Esc 取消选择模式', 'Export PDF': '导出 PDF',
    'Export as…': '导出为…', 'Export options': '导出选项', 'Failed to load': '加载失败',
    'Failed to trigger task': '触发任务失败', 'Family Name': '姓氏',
    'Filter activity…': '筛选活动…', 'Filter by serving engine': '按服务引擎筛选',
    'Font size': '字体大小', 'Google Calendar': 'Google 日历',
    'Hide <label>': '隐藏 <label>', 'Hide Cc/Bcc': '隐藏抄送/密送',
    'Hide email fields': '隐藏邮件字段', 'Hide panel': '隐藏面板',
    'Import failed': '导入失败', 'Import files from disk': '从磁盘导入文件',
    'Import from device': '从设备导入', 'Inject mode': '注入模式',
    'Last active': '最近活跃', 'Load more': '加载更多', 'Loading email': '正在加载邮件',
    'Me / selected account': '我 / 所选账户', 'Memory in context': '上下文中的记忆',
    'Model actions': '模型操作', 'More send options': '更多发送选项',
    'Move to folder': '移动到文件夹', 'Move to folder → New Folder…': '移动到文件夹 → 新文件夹…',
    'Name (optional)': '名称（可选）',
    'Name (optional, e.g. \'Full\' or \'Initials\')': '名称（可选，如「全名」或「缩写」）',
    'New calendar': '新建日历', 'New character...': '新建角色…', 'New document': '新建文档',
    'New document — start typing': '新建文档 — 开始输入', 'New email': '新建邮件',
    'New event': '新建事件', 'New folder': '新建文件夹', 'New item type': '新项类型',
    'Next email': '下一封邮件', 'No folder': '无文件夹', 'Open Visual Report': '打开可视化报告',
    'Open calendar event': '打开日历事件', 'Open chat': '打开对话',
    'Open in Deep Research': '在深度调研中打开', 'Open in Launch': '在启动中打开',
    'Open in OpenStreetMap': '在 OpenStreetMap 打开', 'Open in chat': '在对话中打开',
    'Open in document editor': '在文档编辑器中打开', 'Open in new tab': '在新标签页打开',
    'Open in new window': '在新窗口打开', 'Open task': '打开任务',
    'Open the visual research report': '打开可视化调研报告',
    'Original total model parameters, not quantized storage size.': '原始模型总参数，非量化存储大小。',
    'Passed an automated test': '通过自动化测试', 'Password: value': '密码：值',
    'Pause all active tasks': '暂停所有活跃任务',
    'Permanently delete Odysseus reminder emails': '永久删除 Odysseus 提醒邮件',
    'Preview (Ctrl+Alt+M to toggle)': '预览（Ctrl+Alt+M 切换）', 'Previous email': '上一封邮件',
    'Provider (host:port)': '供应商（host:port）',
    'Refresh cached models on selected server': '刷新所选服务器缓存的模型',
    'Refresh from database': '从数据库刷新', 'Reload PDF view': '重新加载 PDF 视图',
    'Remove tag': '移除标签', 'Remove tag filter': '移除标签筛选', 'Remove this chip': '移除此标签',
    'Reply All': '全部回复', 'Resume project': '恢复项目', 'Run AI edit': '运行 AI 编辑',
    'Run the test again': '重新运行测试', 'SSH port (default 22)': 'SSH 端口（默认 22）',
    'Save (archive)': '保存（归档）', 'Save as Character': '保存为角色',
    'Save as copy': '保存为副本', 'Save current config': '保存当前配置',
    'Save current preset': '保存当前预设', 'Save first': '先保存', 'Save new version': '保存新版本',
    'Save schedule': '保存计划', 'Save server changes': '保存服务器更改',
    'Save this server': '保存此服务器', 'Search albums...': '搜索相册…',
    'Search all events…': '搜索全部事件…', 'Search attachments': '搜索附件',
    'Search by name or text': '按名称或文字搜索',
    'Search contacts (name, email, phone, address)': '搜索联系人（姓名、邮件、电话、地址）',
    'Search notes…': '搜索笔记…', 'Search photos, tags...': '搜索图片、标签…',
    'Search projects…': '搜索项目…', 'Search tasks…': '搜索任务…',
    'Select documents': '选择文档', 'Select for bulk actions': '选择以批量操作',
    'Select model': '选择模型', 'Select sessions': '选择会话', 'Select tasks': '选择任务',
    'Send email (Ctrl+Enter)': '发送邮件（Ctrl+Enter）', 'Send from': '发送自',
    'Send signed reply': '发送签名回复', 'Sent email': '已发送邮件',
    'Serve stopped before the model became reachable': '模型可达前服务已停止',
    'Server color': '服务器颜色', 'Server name': '服务器名称', 'Set to today\'s date': '设为今天日期',
    'Set up SSH key for this server': '为此服务器配置 SSH 密钥',
    'Set up at Settings › Integrations': '在 设置 › 集成 中配置',
    'Set up at: Settings › X': '在：设置 › X 中配置',
    'Show all emails from sender': '显示来自该发件人的全部邮件',
    'Show all tags': '显示全部标签', 'Show email tags': '显示邮件标签',
    'Show less': '显示更少', 'Show more': '显示更多', 'Show notes without tags': '显示无标签笔记',
    'Show only emails not marked as done (undone)': '仅显示未标记完成的邮件',
    'Show only emails with attachments': '仅显示带附件的邮件',
    'Show only goals': '仅显示目标', 'Show recipients': '显示收件人',
    'Show unread emails': '显示未读邮件', 'Sort tasks': '排序任务',
    'Start this queued download now': '立即开始此排队下载', 'Stop this task': '停止此任务',
    'Stroke color': '描边颜色', 'Take a note...': '记一笔…', 'Task completed': '任务完成',
    'Toggle PDF view': '切换 PDF 视图', 'Toggle Window': '切换窗口',
    'Toggle multi-select': '切换多选', 'Toggle view': '切换视图',
    'Token name': '令牌名称', 'Token stored': '已存储令牌',
    'Type a tag and press Enter to add it': '输入标签后按 Enter 添加',
    'Type or paste a folder path, then press Enter': '输入或粘贴文件夹路径后按 Enter',
    'Unarchive note': '取消归档笔记',
    'Unlink from chat (kept in the Library)': '从对话取消链接（保留在资料库）',
    'Untitled photo (press Enter to save)': '未命名图片（按 Enter 保存）',
    'Upload album': '上传相册', 'Upload photos or videos': '上传图片或视频',
    'Uses model': '使用模型', 'Using manual hardware': '使用手动硬件',
    'Version history': '版本历史', 'View <label>': '查看 <label>', 'View Report': '查看报告',
    'View archive': '查看归档', 'View download source on HuggingFace': '在 HuggingFace 查看下载源',
    'View image description': '查看图片描述', 'What does Extract do?': '提取有什么用？',
    'Write language...': '编写语言…', 'Write your note…': '写下你的笔记…',
    'Your Name': '你的姓名',

    // 属性文案（title / placeholder / aria-label）
    'AI expand — turn your notes into a full system prompt': 'AI 展开 — 将笔记转为完整系统提示',
    'AI tidy: deduplicate and clean up memories': 'AI 整理：去重并清理记忆',
    'Add a model to try if the one above fails': '添加上方失败时尝试的备选模型',
    'Add a model to try if the utility model fails': '添加工具模型失败时尝试的备选模型',
    'Add a search provider to try if the primary fails': '添加主搜索失败时尝试的备选搜索',
    'Add a vision model to try if the one above fails': '添加上方视觉模型失败时尝试的备选',
    'Add model endpoints': '添加模型端点', 'Added after your message': '添加在你的消息之后',
    'Added before your message': '添加在你的消息之前',
    'Archive selected': '归档所选', 'Audit selected draft skills': '审计所选草稿技能',
    'Auto-polling every 3 seconds': '每 3 秒自动轮询',
    'Base URL or pick provider': 'Base URL 或选择供应商', 'Chat area': '对话区',
    'Chat context': '对话上下文', 'Chat ready': '对话就绪', 'Clear workspace': '清除工作区',
    'Close cookbook': '关闭模型食谱', 'Close memory modal': '关闭记忆弹窗',
    'Close prompt': '关闭提示', 'Close rename session modal': '关闭重命名会话弹窗',
    'Close settings': '关闭设置', 'Close theme': '关闭主题',
    'Compare active — click to deactivate': '对比已启用 — 点击停用',
    'Compose email': '撰写邮件',
    'Controls randomness. Lower values give focused, deterministic answers (good for code). Higher values give more creative, varied responses.': '控制随机性。值越低越聚焦、确定（适合代码）；值越高越创意、多样。',
    'Create a new persona': '创建新人人格', 'Current password': '当前密码',
    'Deep Research active — click to deactivate': '深度调研已启用 — 点击停用',
    'Delete all calendar': '删除全部日历', 'Delete all chats': '删除全部对话',
    'Delete all documents': '删除全部文档', 'Delete all gallery': '删除全部图库',
    'Delete all memory': '删除全部记忆', 'Delete all notes': '删除全部笔记',
    'Delete all skills': '删除全部技能', 'Delete all tasks': '删除全部任务',
    'Delete every category': '删除每一类', 'Delete everything': '删除所有内容',
    'Delete selected': '删除所选',
    'Delete selected duplicates, generic/irrelevant skills, failed audits, and skills below threshold': '删除所选的重复、通用/无关技能、审计失败及低于阈值的技能',
    'Delete session': '删除会话', 'Delete this persona and its memories': '删除此人格及其记忆',
    'Effect color': '效果颜色', 'Enable Nobody mode — no memory, no history saved': '启用隐身模式 — 不保存记忆与历史',
    'Enter custom value': '输入自定义值', 'Enter session name': '输入会话名称',
    'Export all memories as JSON': '将所有记忆导出为 JSON',
    'Export current colors as JSON': '将当前颜色导出为 JSON',
    'Fade this window to preview the page behind it': '淡出此窗口以预览其后页面',
    'Fill the default Ollama endpoint': '填入默认 Ollama 端点',
    'Give your persona a name...': '给你的角色起个名…',
    'Google PSE engine ID': 'Google PSE 引擎 ID', 'Grant full admin access': '授予完全管理员权限',
    'Group Chat active — click to deactivate': '群组对话已启用 — 点击停用',
    'Hamburger menu': '汉堡菜单',
    'How long the researcher waits for a single URL to fetch and extract before giving up on it. Slow sites get skipped. Default 90 seconds.': '研究者等待单个 URL 抓取提取的时长，超时放弃。慢站点被跳过。默认 90 秒。',
    'How many URLs the researcher fetches and extracts in parallel. Higher is faster but uses more memory/CPU. Default 3.': '研究者并行抓取提取的 URL 数。越大越快但更耗内存/CPU。默认 3。',
    'How many web search results to fetch per query': '每次查询抓取的网页搜索结果数',
    'How — the approach or steps': '如何 — 方法或步骤',
    'Import a theme from JSON': '从 JSON 导入主题', 'Import memories from a file': '从文件导入记忆',
    'Import skill from URL': '从 URL 导入技能', 'Include memories in chat context': '在对话上下文中包含记忆',
    'Inject relevant skills into chat context': '在对话上下文中注入相关技能',
    'Manage Chats (Library)': '管理对话（资料库）', 'Max skills to inject': '最大注入技能数',
    'Maximum length of the AI response. \'No limit\' lets the model decide when to stop.': 'AI 回复的最大长度。「无限制」让模型自行决定何时停止。',
    'Memory category': '记忆类别', 'Message Odysseus...': '给 Odysseus 发消息…',
    'Message input': '消息输入', 'More': '更多', 'More options': '更多选项',
    'More tools': '更多工具', 'New chat': '新建对话', 'New document': '新建文档',
    'New memory text': '新记忆文本', 'New password': '新密码',
    'Nobody mode active — click to deactivate': '隐身模式已启用 — 点击停用',
    'Open email inbox': '打开收件箱',
    'Optional — write the reminder in the voice of a saved character': '可选 — 以已存角色口吻写提醒',
    'Password': '密码',
    'Paste endpoint URL, e.g. http://localhost:11434/v1': '粘贴端点 URL，如 http://localhost:11434/v1',
    'Paste theme JSON here...': '在此粘贴主题 JSON…',
    'Persona active — click to deactivate': '人格已启用 — 点击停用',
    'Pick provider': '选择供应商', 'Prompt': '提示',
    'Providers tried in order when the primary fails or hits a rate limit': '主供应商失败或限流时依次尝试的供应商',
    'Publish selected drafts': '发布所选草稿',
    'RAG active — click to deactivate': '知识库检索已启用 — 点击停用',
    'Re-test every endpoint and refresh online status': '重新测试每个端点并刷新在线状态',
    'Refresh model picker': '刷新模型选择器',
    'Remove all endpoints currently marked offline': '移除当前标记离线的所有端点',
    'Rename session': '重命名会话', 'Reset Chat Area to defaults': '重置对话区为默认',
    'Reset Chat Bar to defaults': '重置对话栏为默认', 'Reset Sidebar to defaults': '重置侧边栏为默认',
    'Reset color': '重置颜色', 'Reset shortcuts to defaults': '重置快捷键为默认',
    'Reset this color': '重置此颜色', 'Reset this section to defaults': '重置此分区为默认',
    'Reset to default': '重置为默认', 'Reset to text color': '重置为文字颜色',
    'Run a test query against the configured provider': '对配置的供应商运行测试查询',
    'Scan your network for running model servers': '扫描网络中运行的模型服务',
    'Scroll to bottom': '滚动到底部',
    'Search conversations (Ctrl+K)': '搜索对话（Ctrl+K）',
    'Search conversations...': '搜索对话…', 'Search logs...': '搜索日志…',
    'Search memories': '搜索记忆', 'Search memories…': '搜索记忆…',
    'Search models': '搜索模型', 'Search models...': '搜索模型…',
    'Search skills': '搜索技能', 'Search skills…': '搜索技能…',
    'Select multiple memories': '选择多条记忆', 'Select multiple skills': '选择多个技能',
    'Shell Access': '终端访问', 'Shell access': '终端访问',
    'Show / hide the API key field': '显示/隐藏 API 密钥字段', 'Show sidebar': '显示侧边栏',
    'Skill import URL': '技能导入 URL', 'Skill title': '技能标题',
    'Sort memories': '排序记忆', 'Sort sessions': '排序会话', 'Switch model': '切换模型',
    'Tags': '标签', 'Test every skill, auto-fix the weak ones, flag what still fails': '测试每个技能，自动修复薄弱项，标记仍失败的',
    'Text size': '文字大小', 'Theme name...': '主题名称…', 'Toggle sidebar': '切换侧边栏',
    'Turn off plan mode': '关闭计划模式',
    'Use the utility model to write reminder messages': '使用工具模型写提醒消息',
    'Username': '用户名', 'Web search': '联网搜索', 'When to use this skill': '何时使用此技能',
    'Workspace - click to clear': '工作区 - 点击清除',
    'Write rough notes and click Expand, or leave empty': '写粗略笔记并点击展开，或留空',
    'API key': 'API 密钥',
    'API key (optional — for protected local endpoints)': 'API 密钥（可选 — 用于受保护的本地端点）',
    'API key, e.g. sk-proj-AbCdEf…': 'API 密钥，如 sk-proj-AbCdEf…'
  };

  // ---- 带变量的 UI 模式（仅非聊天容器，格式高度特定，误翻风险极低）----
  var PATTERNS = [
    { re: /^(\d+) Selected$/, fn: function (m) { return '已选 ' + m[1]; } },
    { re: /^(\d+) lines?$/, fn: function (m) { return m[1] + ' 行'; } },
    { re: /^Confidence ≤ (\d+)%$/, fn: function (m) { return '置信度 ≤ ' + m[1] + '%'; } },
    { re: /^No (.+) yet\.$/, fn: function (m) { return '还没有 ' + m[1] + '。'; } },
    { re: /^Search (.+?)\.\.\.$/, fn: function (m) { return '搜索 ' + m[1] + '…'; } },
    { re: /^Filter (.+?)\.\.\.$/, fn: function (m) { return '筛选 ' + m[1] + '…'; } },
    { re: /^(\d+)%$/, fn: function (m) { return m[1] + '%'; } }
  ];

  function inSkip(node) {
    try {
      var el = node.nodeType === 1 ? node : node.parentElement;
      return !!(el && el.closest && el.closest(SKIP));
    } catch (e) { return false; }
  }

  function tr(text) {
    if (!text) return text;
    var t = text.trim();
    if (DICT[t] !== undefined) {
      return text.replace(t, DICT[t]);
    }
    for (var i = 0; i < PATTERNS.length; i++) {
      var m = t.match(PATTERNS[i].re);
      if (m) {
        var out = PATTERNS[i].fn(m);
        return text.replace(t, out);
      }
    }
    return text;
  }

  function walk(root) {
    if (!root) return;
    var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, null, false);
    var node;
    var batch = [];
    while ((node = walker.nextNode())) {
      if (!node.nodeValue || !node.nodeValue.trim()) continue;
      if (inSkip(node)) continue;
      batch.push(node);
    }
    for (var i = 0; i < batch.length; i++) {
      var n = batch[i];
      var nv = n.nodeValue;
      var after = tr(nv);
      if (after !== nv) n.nodeValue = after;
    }
  }

  function walkAttrs(root) {
    if (!root) return;
    var els = root.querySelectorAll('[title],[placeholder],[aria-label]');
    for (var i = 0; i < els.length; i++) {
      var el = els[i];
      if (inSkip(el)) continue;
      ['title', 'placeholder', 'aria-label'].forEach(function (attr) {
        if (el.hasAttribute(attr)) {
          var v = el.getAttribute(attr);
          var a = tr(v);
          if (a !== v) el.setAttribute(attr, a);
        }
      });
    }
  }

  function run() {
    walk(document.body);
    walkAttrs(document.body);
  }

  // 首次运行
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', run);
  } else {
    run();
  }

  // 常驻兜底：仅处理非聊天容器新增节点（动态弹窗也会翻；流式回复命中 SKIP 被丢弃）
  var mo = new MutationObserver(function (mutations) {
    var touched = false;
    for (var i = 0; i < mutations.length; i++) {
      var m = mutations[i];
      if (m.type === 'attributes') {
        var tgt = m.target;
        if (tgt && tgt.nodeType === 1 && !inSkip(tgt)) {
          ['title', 'placeholder', 'aria-label'].forEach(function (attr) {
            if (tgt.hasAttribute(attr) && m.attributeName === attr) {
              var v = tgt.getAttribute(attr);
              var a = tr(v);
              if (a !== v) tgt.setAttribute(attr, a);
            }
          });
        }
        continue;
      }
      var nodes = m.addedNodes;
      for (var j = 0; j < nodes.length; j++) {
        var node = nodes[j];
        if (node.nodeType === 3) {
          if (!inSkip(node)) {
            var nv = node.nodeValue; var after = tr(nv);
            if (after !== nv) node.nodeValue = after;
          }
        } else if (node.nodeType === 1 && !inSkip(node)) {
          walk(node);
          walkAttrs(node);
        }
      }
    }
  });
  mo.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['title', 'placeholder', 'aria-label'] });
})();
