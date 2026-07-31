#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Odysseus 界面中文化补丁脚本。
 Odysseus 没有 i18n，英文 UI 硬编码在 static/js/ 里。本脚本把源文件中的英文 UI 文案直接替换为中文，从根本上避免中英夹杂。
 用法：python apply_zh_patch.py
 注意：git pull 更新后需重新运行此脚本（更新会覆盖 static/js/ 的修改）。
"""
import os

BASE = os.path.dirname(os.path.abspath(__file__))


def patch_calendar():
    path = os.path.join(BASE, 'static', 'js', 'calendar.js')
    with open(path, 'r', encoding='utf-8') as f:
        s = f.read()

    # 定位事件表单模板范围，避免误伤其他代码
    lines = s.split('\n')
    start_idx = None
    end_idx = None
    for i, line in enumerate(lines):
        if 'cal-hero' in line and start_idx is None:
            start_idx = i
        if 'cal-form-actions' in line and end_idx is None:
            end_idx = i + 6  # 包含 Save/Create 按钮
    if start_idx is None or end_idx is None:
        print('[calendar.js] 未找到事件表单范围，跳过')
        return

    block = '\n'.join(lines[start_idx:end_idx])
    repls = [
        ('placeholder="Location"', 'placeholder="地点"'),
        ('placeholder="Description"', 'placeholder="描述"'),
        ("What’s happening?", '在做什么？'),
        ('Event title', '事件标题'),
        ('<span style="opacity:0.3">to</span>', '<span style="opacity:0.3">至</span>'),
        ('All day', '全天'),
        ('Does not repeat', '不重复'),
        ('Daily', '每天'),
        ('Weekly', '每周'),
        ('Weekdays', '工作日'),
        ('Monthly', '每月'),
        ('Yearly', '每年'),
        ('Open in Maps', '在地图中打开'),
        ('Open in Apple Maps', '在 Apple 地图中打开'),
        ('Open in Tasks', '在任务中打开'),
        ('Linked to a Cookbook scheduled task', '链接到 Cookbook 计划任务'),
        ('>Reminder<', '>提醒<'),
        ('No reminder', '无提醒'),
        ('At event time', '事件发生时'),
        ('5 minutes before', '提前 5 分钟'),
        ('10 minutes before', '提前 10 分钟'),
        ('15 minutes before', '提前 15 分钟'),
        ('30 minutes before', '提前 30 分钟'),
        ('1 hour before', '提前 1 小时'),
        ('2 hours before', '提前 2 小时'),
        ('1 day before', '提前 1 天'),
        ('Exact time...', '指定时间...'),
        ('>Color<', '>颜色<'),
        ('>Delete<', '>删除<'),
        ('>Cancel<', '>取消<'),
        ('</svg>Save', '</svg>保存'),
        ('</svg>Create', '</svg>创建'),
    ]
    for old, new in repls:
        block = block.replace(old, new)
    lines[start_idx:end_idx] = block.split('\n')

    with open(path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines))
    print('[calendar.js] 已中文化')


def patch_cookbook():
    path = os.path.join(BASE, 'static', 'js', 'cookbook.js')
    with open(path, 'r', encoding='utf-8') as f:
        s = f.read()

    repls = [
        # 标签页
        ('>Launch</button>', '>启动</button>'),
        ('>Download</button>', '>下载</button>'),
        ('>Dependencies</button>', '>依赖</button>'),
        ('>Dependencies</h2>', '>依赖</h2>'),
        ('>Settings</button>', '>设置</button>'),
        # Direct Download 区域
        ('>Direct Download<', '>直接下载<'),
        ('by pasting model link, or download directly in the Scan section below.', '粘贴模型链接下载，或直接在下方扫描区域下载。'),
        ('placeholder="org/model-name, qwen2.5:14b, or HF URL"', 'placeholder="org/模型名称, qwen2.5:14b, 或 HF URL"'),
        ('>Trending models that fit your hardware</span>', '>适合你硬件的趋势模型</span>'),
        # Scan / Download 区域
        ('>Scan / Download<', '>扫描 / 下载<'),
        ('Scans your hardware for what models you can run. Hardware is cached; hit the scan button to re-probe after changing GPUs.', '扫描你的硬件，找出可运行的模型。硬件信息已缓存；更换 GPU 后点击扫描按钮重新探测。'),
        ('placeholder="Search models..."', 'placeholder="搜索模型…"'),
        ('>Standard</option>', '>标准</option>'),
        ('>Vision</option>', '>视觉</option>'),
        ('>Image</option>', '>图像</option>'),
        ('title="Model type"', 'title="模型类型"'),
        ('>EDIT</button>', '>编辑</button>'),
        ('title="Set hardware manually"', 'title="手动设置硬件"'),
        ('title="Scan settings"', 'title="扫描设置"'),
        ('aria-label="Scan settings"', 'aria-label="扫描设置"'),
        ('title="Refresh selected server hardware and cached models"', 'title="刷新所选服务器硬件和缓存模型"'),
        ('aria-label="Refresh selected server hardware and cached models"', 'aria-label="刷新所选服务器硬件和缓存模型"'),
        ('>Latest</option>', '>最新</option>'),
        ('>Fit</option>', '>适配</option>'),
        ('>Score</option>', '>评分</option>'),
        ('>VRAM</option>', '>显存</option>'),
        ('<span style="font-size:10px;opacity:0.5;margin-left:auto;">Server</span>', '<span style="font-size:10px;opacity:0.5;margin-left:auto;">服务器</span>'),
        # 状态/错误提示
        ("Couldn't load trending models", '无法加载趋势模型'),
        ('No trending models found', '未找到趋势模型'),
        (' downloads', ' 下载'),
        ('Failed to load', '加载失败'),
        ('No models', '无模型'),
        ('Loading…', '加载中…'),
    ]
    for old, new in repls:
        s = s.replace(old, new)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(s)
    print('[cookbook.js] 已中文化')


def patch_cookbook_hwfit():
    path = os.path.join(BASE, 'static', 'js', 'cookbook-hwfit.js')
    if not os.path.exists(path):
        print('[cookbook-hwfit.js] 文件不存在，跳过')
        return
    with open(path, 'r', encoding='utf-8') as f:
        s = f.read()

    repls = [
        ('Scanning hardware…', '正在扫描硬件…'),
        ('Loading models…', '正在加载模型…'),
        ('Loading model list…', '正在加载模型列表…'),
        ('No models', '无模型'),
        (' downloads', ' 下载'),
        ('>Download</button>', '>下载</button>'),
    ]
    for old, new in repls:
        s = s.replace(old, new)

    with open(path, 'w', encoding='utf-8') as f:
        f.write(s)
    print('[cookbook-hwfit.js] 已中文化')


if __name__ == '__main__':
    patch_calendar()
    patch_cookbook()
    patch_cookbook_hwfit()
    print('\n中文化完成。请强刷浏览器 (Ctrl+F5) 查看效果。')
