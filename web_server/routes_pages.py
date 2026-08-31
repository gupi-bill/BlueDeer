# 自动拆分自 web_server.py（路由域: pages）
import asyncio
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from web_server.app import (
    app,
    debugger,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> str:
    """BlueDeer 控制台（OpenClaw 风格，内含办公室平面图视图）。"""
    html = await asyncio.to_thread(
        lambda: open("templates/project_hub.html", "r", encoding="utf-8").read()
    )
    return html


@router.get("/office", response_class=HTMLResponse)
async def office_workspace(request: Request) -> str:
    """办公工作空间：代码编辑 + Agent 协作 + 文档生成 + 任务管理。"""
    html = await asyncio.to_thread(
        lambda: open("templates/office_workspace.html", "r", encoding="utf-8").read()
    )
    return html


@router.get("/floorplan", response_class=HTMLResponse)
async def floorplan_page(request: Request) -> str:
    """2.5D 办公室平面图（供首页 iframe 嵌入）。"""
    html = (
        """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BlueDeer 森林公司 · 平面图</title>
<style>
* { margin:0; padding:0; box-sizing:border-box; }
body {
    font-family: 'Segoe UI','Microsoft YaHei',system-ui,sans-serif;
    background: #efe5d8;
    color: #d8f0d8;
    min-height: 100vh;
    overflow-x: auto;
}

/* ===== 全局动画 ===== */
@keyframes floatSteam {
    0% { transform: translateY(0) scale(1); opacity: 0.7; }
    50% { transform: translateY(-16px) scale(1.3); opacity: 0.4; }
    100% { transform: translateY(-32px) scale(1.7); opacity: 0; }
}
@keyframes breathe {
    0%,100% { opacity: 0.35; }
    50% { opacity: 0.9; }
}
@keyframes screenGlow {
    0%,100% { filter: brightness(0.9); }
    50% { filter: brightness(1.3); }
}
@keyframes swim {
    0% { transform: translateX(0) translateY(0); }
    25% { transform: translateX(60px) translateY(-4px); }
    50% { transform: translateX(120px) translateY(0); }
    75% { transform: translateX(60px) translateY(4px); }
    100% { transform: translateX(0) translateY(0); }
}
@keyframes waterRipple {
    0%,100% { transform: scale(0.7); opacity: 0.25; }
    50% { transform: scale(1.3); opacity: 0.6; }
}
@keyframes sunbeam {
    0% { transform: translateX(-40px) rotate(25deg); opacity: 0.15; }
    50% { transform: translateX(0) rotate(25deg); opacity: 0.3; }
    100% { transform: translateX(40px) rotate(25deg); opacity: 0.15; }
}
@keyframes statusPulse {
    0%,100% { box-shadow: 0 0 4px #4caf50; }
    50% { box-shadow: 0 0 14px #76ff03; }
}
@keyframes flicker {
    0%,100% { opacity: 0.75; }
    50% { opacity: 0.95; }
}
@keyframes floatCloud {
    0%,100% { transform: translateX(0); }
    50% { transform: translateX(15px); }
}
@keyframes sway {
    0%,100% { transform: rotate(-2deg); }
    50% { transform: rotate(2deg); }
}
@keyframes leafFall {
    0% { transform: translateY(0) rotate(0); opacity: 0.8; }
    100% { transform: translateY(30px) rotate(45deg); opacity: 0; }
}

.floorplan-wrapper {
    padding: 30px;
    min-width: 1200px;
    min-height: 100vh;
    display: flex;
    flex-direction: column;
}
.floorplan {
    position: relative;
    width: 1140px;
    height: 800px;
    margin: 0 auto;
    background:
        repeating-linear-gradient(90deg, rgba(0,0,0,0.05) 0 1px, transparent 1px 40px),
        repeating-linear-gradient(0deg, rgba(0,0,0,0.05) 0 1px, transparent 1px 40px),
        linear-gradient(135deg, #d7ccc8 0%, #bcaaa4 100%);
    border: 8px solid #5d4037;
    border-radius: 8px;
    box-shadow: 0 20px 60px rgba(0,0,0,0.6), inset 0 0 120px rgba(0,0,0,0.15);
    overflow: hidden;
    flex-shrink: 0;
}

/* 墙体 */
.wall {
    position: absolute;
    background: #4e342e;
    box-shadow: inset 0 0 10px rgba(0,0,0,0.3);
}
.wall-h { height: 8px; }
.wall-v { width: 8px; }

/* 窗户阳光 */
.window-light {
    position: absolute;
    width: 220px;
    height: 500px;
    background: linear-gradient(90deg, rgba(255,248,220,0) 0%, rgba(255,248,220,0.18) 50%, rgba(255,248,220,0) 100%);
    transform: rotate(25deg);
    filter: blur(10px);
    animation: sunbeam 10s ease-in-out infinite;
    pointer-events: none;
    z-index: 5;
}

/* 房间区域 */
.room {
    position: absolute;
    border: 2px dashed rgba(93,64,55,0.25);
    transition: all 0.25s ease;
    cursor: pointer;
}
.room:hover {
    background: rgba(76,175,80,0.06);
    border-color: rgba(76,175,80,0.5);
    box-shadow: inset 0 0 30px rgba(76,175,80,0.1);
}
.room-label {
    position: absolute;
    font-size: 13px;
    font-weight: 700;
    color: #3e2723;
    text-shadow: 0 1px 0 rgba(255,255,255,0.4);
    pointer-events: none;
    letter-spacing: 1px;
    z-index: 20;
}

/* ==================== 资料库 Library ==================== */
#library { left: 30px; top: 30px; width: 260px; height: 240px; background: #efebe9; }

/* 三面书墙 */
.book-wall {
    position: absolute;
    background:
        repeating-linear-gradient(0deg, #4e342e 0 3px, transparent 3px 56px),
        #5d4037;
    border-radius: 3px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.12), inset 0 0 10px rgba(0,0,0,0.3);
}
.book-wall::before {
    content: "";
    position: absolute;
    left: -3px; right: -3px; top: 0; bottom: 0;
    border: 2px solid #4e342e;
    border-radius: 3px;
    pointer-events: none;
}
.book-wall-left {
    left: 12px; top: 35px;
    width: 55px; height: 175px;
}
.book-wall-back {
    left: 72px; top: 35px;
    width: 130px; height: 45px;
}
.book-wall-right {
    right: 12px; top: 35px;
    width: 40px; height: 120px;
}

/* 彩色书脊 */
.books {
    position: absolute;
    display: flex;
    flex-direction: column;
    gap: 2px;
    padding: 4px;
}
.book-spine {
    width: 100%;
    height: 14px;
    border-radius: 1px 1px 0 0;
    border-left: 3px solid rgba(255,255,255,0.3);
    box-shadow: inset -2px 0 0 rgba(0,0,0,0.2), inset 0 2px 0 rgba(255,255,255,0.18);
    position: relative;
}
.book-spine::after {
    content: "";
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 40%; height: 2px;
    background: rgba(255,255,255,0.25);
}

/* 阅读区大桌 */
.reading-table {
    position: absolute;
    right: 22px; bottom: 28px;
    width: 110px; height: 75px;
    background: #8d6e63;
    border-radius: 4px;
    box-shadow: 5px 5px 0 rgba(0,0,0,0.15);
}
.reading-table::before {
    content: "";
    position: absolute;
    left: 8px; top: -6px;
    width: 94px; height: 12px;
    background: #a1887f;
    border-radius: 2px;
}
.reading-table::after {
    content: "";
    position: absolute;
    left: 35px; top: -26px;
    width: 24px; height: 24px;
    background: #fff9c4;
    border-radius: 50%;
    box-shadow: 0 0 25px #fff59d;
    animation: flicker 3s ease-in-out infinite;
}

/* 桌上物品 */
.open-book {
    position: absolute;
    left: 12px; top: 18px;
    width: 34px; height: 24px;
    background: #fff;
    border-radius: 2px;
    box-shadow: 1px 1px 3px rgba(0,0,0,0.1);
}
.open-book::before {
    content: "";
    position: absolute;
    left: 50%; top: 2px; bottom: 2px;
    width: 1px;
    background: #d7ccc8;
}
.glasses {
    position: absolute;
    right: 14px; top: 22px;
    width: 22px; height: 8px;
    border: 2px solid #424242;
    border-radius: 8px;
}
.globe {
    position: absolute;
    left: 55px; top: 10px;
    width: 18px; height: 18px;
    background: radial-gradient(circle at 30% 30%, #4fc3f7, #0277bd);
    border-radius: 50%;
    border: 2px solid #6d4c41;
}
.globe::after {
    content: "";
    position: absolute;
    left: 50%; bottom: -8px;
    transform: translateX(-50%);
    width: 4px; height: 10px;
    background: #6d4c41;
}

/* 梯子和分类标签 */
.ladder {
    position: absolute;
    left: 75px; top: 90px;
    width: 8px; height: 120px;
    background: #6d4c41;
    transform: rotate(10deg);
}
.ladder::before {
    content: "";
    position: absolute;
    left: -12px; top: 0; bottom: 0;
    width: 32px;
    background: repeating-linear-gradient(0deg, transparent 0 22px, #6d4c41 22px 26px);
}
.shelf-label {
    position: absolute;
    font-size: 8px;
    color: #5d4037;
    background: #fff9c4;
    padding: 1px 4px;
    border-radius: 2px;
    font-weight: 700;
}

/* 知识树挂画 */
.knowledge-tree {
    position: absolute;
    right: 18px; top: 45px;
    width: 55px; height: 70px;
    background: #fff;
    border: 3px solid #6d4c41;
    border-radius: 3px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}
.knowledge-tree::before {
    content: "知识树";
    position: absolute;
    bottom: 3px;
    font-size: 8px;
    color: #5d4037;
}

/* 盆栽 */
.pot-plant {
    position: absolute;
    font-size: 22px;
    line-height: 1;
    animation: sway 4s ease-in-out infinite;
}

/* ==================== 总经理办公室 CEO ==================== */
#ceo { right: 30px; top: 30px; width: 380px; height: 240px; background: #efebe9; }
#ceo .ceo-desk {
    position: absolute;
    right: 45px; top: 65px;
    width: 170px; height: 95px;
    background: #6d4c41;
    border-radius: 4px;
    box-shadow: 6px 6px 0 rgba(0,0,0,0.15);
}
#ceo .ceo-desk::before {
    content: "";
    position: absolute;
    left: 25px; top: 18px;
    width: 90px; height: 55px;
    background: #263238;
    border-radius: 3px;
    animation: screenGlow 4s ease-in-out infinite;
}
#ceo .ceo-desk::after {
    content: "";
    position: absolute;
    right: 12px; top: 25px;
    width: 28px; height: 40px;
    background: #fff;
    border-radius: 2px;
    box-shadow: 1px 1px 3px rgba(0,0,0,0.15);
}
#ceo .ceo-chair {
    position: absolute;
    right: 110px; bottom: 28px;
    width: 55px; height: 55px;
    background: #3e2723;
    border-radius: 50% 50% 10px 10px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.15);
}
#ceo .deer-badge {
    position: absolute;
    left: 25px; top: 50px;
    width: 70px; height: 90px;
    background: #fff;
    border: 2px solid #5d4037;
    border-radius: 6px;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-size: 28px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
#ceo .deer-badge::after {
    content: "总经理";
    font-size: 11px;
    color: #5d4037;
    margin-top: 4px;
    font-weight: 700;
}
#ceo .deer-badge img {
    width: 85%; height: 70%;
    object-fit: contain;
    image-rendering: pixelated;
}
#ceo .window {
    position: absolute;
    right: 0; top: 25px;
    width: 16px; height: 150px;
    background: linear-gradient(180deg, #b3e5fc, #81d4fa);
    border-left: 3px solid #5d4037;
}
#ceo .window::before {
    content: "";
    position: absolute;
    right: 4px; top: 25px;
    width: 24px; height: 24px;
    background: radial-gradient(circle at 30% 70%, rgba(255,255,255,0.7), transparent 50%);
    border-radius: 50%;
    opacity: 0.5;
}
#ceo .window::after {
    content: "";
    position: absolute;
    right: 2px; top: 60px;
    width: 18px; height: 12px;
    background: linear-gradient(90deg, rgba(255,255,255,0.6), transparent);
    border-radius: 50%;
    opacity: 0.4;
    animation: floatCloud 8s ease-in-out infinite;
}
#ceo .bookshelf-small {
    position: absolute;
    left: 115px; top: 60px;
    width: 55px; height: 90px;
    background: #5d4037;
    border-radius: 3px;
}
#ceo .bookshelf-small::before {
    content: "";
    position: absolute;
    left: 3px; top: 6px; right: 3px; bottom: 6px;
    background: repeating-linear-gradient(0deg, #8d6e63 0 5px, #5d4037 5px 8px, #a1887f 8px 13px, #4e342e 13px 18px);
}
#ceo .trophy {
    position: absolute;
    left: 130px; top: 42px;
    font-size: 20px;
}
#ceo .strategy-board {
    position: absolute;
    left: 190px; top: 12px;
    width: 90px; height: 55px;
    background: #fff;
    border: 3px solid #6d4c41;
    border-radius: 3px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 24px;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}
#ceo .strategy-board::after {
    content: "战略图";
    position: absolute;
    bottom: 2px;
    font-size: 8px;
    color: #5d4037;
}

/* ==================== 调度室 Dispatch ==================== */
#dispatch { left: 310px; top: 35px; width: 400px; height: 230px; background: #efebe9; }
#dispatch .dispatch-desk {
    position: absolute;
    left: 50px; top: 92px;
    width: 200px; height: 104px;
    background: #ffffff;
    border: 1px solid #e6eaf0;
    border-radius: 14px;
    box-shadow: 0 4px 16px rgba(31,41,55,0.12);
}
#dispatch .dispatch-screen {
    position: absolute;
    background: #263238;
    border-radius: 3px;
    border: 2px solid #455a64;
    animation: screenGlow 4s ease-in-out infinite;
}
#dispatch .dispatch-screen.main {
    left: 16px; top: -58px;
    width: 86px; height: 56px;
    box-shadow: 0 0 14px rgba(105,240,174,0.3);
}
#dispatch .dispatch-screen.main::after {
    content: "</>";
    position: absolute;
    left: 22px; top: 18px;
    font-size: 12px; color: #69f0ae;
    font-family: monospace;
}
#dispatch .dispatch-screen.side {
    right: 14px; top: -44px;
    width: 54px; height: 40px;
    background: #1a237e;
    border-color: #3949ab;
    animation-delay: 1.2s;
}
#dispatch .dispatch-screen.side::after {
    content: "";
    position: absolute;
    left: 8px; top: 6px;
    width: 38px; height: 28px;
    background:
        linear-gradient(90deg, rgba(129,199,132,0.6) 0 25%, transparent 25% 50%, rgba(255,167,38,0.6) 50% 75%, transparent 75% 100%),
        repeating-linear-gradient(0deg, rgba(255,255,255,0.2) 0 2px, transparent 2px 6px);
    border-radius: 2px;
}
#dispatch .dispatch-keyboard {
    position: absolute;
    left: 18px; top: 14px;
    width: 90px; height: 16px;
    background: #5d4037;
    border-radius: 2px;
    box-shadow: inset 0 0 0 1px rgba(0,0,0,0.2);
}
#dispatch .dispatch-chair {
    position: absolute;
    left: 113px; bottom: -30px;
    width: 48px; height: 48px;
    background: #3e2723;
    border-radius: 50% 50% 10px 10px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.15);
}
#dispatch .dispatch-board {
    position: absolute;
    right: 16px; top: 26px;
    width: 96px; height: 64px;
    background: #fafafa;
    border: 3px solid #6d4c41;
    border-radius: 3px;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}
#dispatch .dispatch-board::after {
    content: "排期看板";
    position: absolute;
    bottom: 2px; right: 3px;
    font-size: 8px; color: #5d4037;
}
#dispatch .task-strip {
    position: absolute;
    height: 4px;
    border-radius: 2px;
}
#dispatch .world-pin {
    position: absolute;
    left: 18px; top: 30px;
    width: 40px; height: 40px;
    background: radial-gradient(circle at 50% 40%, #a5d6a7 0 60%, #81c784 61% 100%);
    border: 2px solid #4e342e;
    border-radius: 50%;
    box-shadow: 1px 1px 3px rgba(0,0,0,0.15);
}
#dispatch .world-pin::after {
    content: "";
    position: absolute;
    left: 8px; top: 6px;
    width: 24px; height: 24px;
    background:
        linear-gradient(135deg, transparent 45%, rgba(76,175,80,0.6) 45% 55%, transparent 55%),
        linear-gradient(45deg, transparent 45%, rgba(76,175,80,0.6) 45% 55%, transparent 55%),
        radial-gradient(circle at 50% 50%, rgba(255,255,255,0.4), transparent 70%);
    border-radius: 50%;
}

/* ==================== 开放办公区 ==================== */
#office-area { left: 30px; top: 300px; width: 700px; height: 340px; background: #eef1f4; }
.emp-card {
    position: absolute;
    width: 140px; height: 150px;
    background: #ffffff;
    border: 1px solid #eef1f6;
    border-radius: 18px;
    box-shadow: 0 1px 2px rgba(16,24,40,0.05), 0 8px 20px rgba(16,24,40,0.07);
    cursor: pointer;
    transition: transform 0.2s cubic-bezier(.2,.7,.3,1), box-shadow 0.2s ease;
    overflow: hidden;
    display: flex;
    flex-direction: column;
    align-items: center;
}
.emp-card:hover { transform: translateY(-6px); box-shadow: 0 6px 12px rgba(16,24,40,0.08), 0 20px 40px rgba(16,24,40,0.14); z-index: 60; }
.desk-stage { width: 140px; height: 108px; }
.desk-svg { width: 140px; height: 108px; display: block; }
.emp-card .ename { margin-top: 1px; font-size: 12.5px; font-weight: 700; color: #0f172a; letter-spacing: 0.2px; }
.emp-card .erole { margin-top: 1px; font-size: 9px; color: #94a3b8; font-weight: 500; }
@keyframes lampPulse { 0%,100% { opacity: 1; } 50% { opacity: 0.32; } }
.lamp { animation: lampPulse 2.4s ease-in-out infinite; }
.lamp.online { fill: #22c55e; }
.lamp.busy { fill: #f59e0b; }
.lamp.idle { fill: #94a3b8; }
.lamp.onduty { fill: #60a5fa; }
.desk-photo {
    width: 100%; height: 100%;
    object-fit: contain;
    image-rendering: pixelated;
}

.room-char {
    position: absolute;
    width: 58px; height: 72px;
    background: #ffffff;
    border: 1px solid #eef1f6;
    border-radius: 14px;
    box-shadow: 0 3px 10px rgba(16,24,40,0.10);
    cursor: pointer;
    overflow: hidden;
    display: flex; flex-direction: column; align-items: center; padding-top: 7px;
}
.room-char .desk-photo {
    width: 42px; height: 42px;
    object-fit: contain; image-rendering: pixelated;
}
.room-char-cap {
    position: static;
    margin-top: 4px;
    text-align: center;
    font-size: 9px;
    color: #0f172a;
    font-weight: 700;
    white-space: nowrap;
    line-height: 1.2;
}
.room-char-cap span {
    font-size: 8px;
    color: #94a3b8;
    font-weight: 500;
}

/* 工位空闲态：人仍在工位待命，仅整体阴影更轻表示安静 */
.emp-card.idle { box-shadow: 0 1px 2px rgba(16,24,40,0.04), 0 4px 12px rgba(16,24,40,0.04); }

/* ==================== 茶水间 ==================== */
#breakroom { left: 30px; top: 650px; width: 360px; height: 120px; background: #efebe9; }
#breakroom .counter {
    position: absolute;
    left: 15px; top: 15px;
    width: 170px; height: 58px;
    background: #8d6e63;
    border-radius: 4px;
    box-shadow: 4px 4px 0 rgba(0,0,0,0.12);
}
.coffee-machine {
    position: absolute;
    left: 20px; top: -22px;
    width: 34px; height: 34px;
    background: #424242;
    border-radius: 4px;
}
.coffee-machine::after {
    content: "☕";
    position: absolute;
    left: 5px; top: 5px;
    font-size: 18px;
}
.microwave {
    position: absolute;
    left: 62px; top: -16px;
    width: 36px; height: 24px;
    background: #bdbdbd;
    border-radius: 3px;
    border: 2px solid #757575;
}
.microwave::after {
    content: "";
    position: absolute;
    right: 4px; top: 4px;
    width: 20px; height: 12px;
    background: #424242;
    border-radius: 1px;
}
.water-dispenser {
    position: absolute;
    left: 110px; top: -28px;
    width: 22px; height: 42px;
    background: #4fc3f7;
    border-radius: 3px;
    border: 2px solid #0277bd;
}
.water-dispenser::after {
    content: "";
    position: absolute;
    left: 50%; top: 8px;
    transform: translateX(-50%);
    width: 10px; height: 10px;
    background: #fff;
    border-radius: 50%;
}
.stool {
    position: absolute;
    width: 22px; height: 22px;
    background: #5d4037;
    border-radius: 50%;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.1);
}
.notice-board {
    position: absolute;
    right: 18px; top: 12px;
    width: 130px; height: 75px;
    background: #d7ccc8;
    border: 3px solid #6d4c41;
    border-radius: 4px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
    display: flex;
    flex-wrap: wrap;
    padding: 5px;
    gap: 5px;
}
.notice-board::before {
    content: "公告";
    position: absolute;
    top: -12px; left: 8px;
    background: #5d4037;
    color: #fff;
    font-size: 9px;
    padding: 1px 6px;
    border-radius: 2px;
}
.notice-paper {
    width: 22px; height: 26px;
    background: #fff;
    border: 1px solid #bcaaa4;
}
.notice-paper:nth-child(2) { background: #fff9c4; transform: rotate(-3deg); }
.notice-paper:nth-child(3) { background: #ffccbc; transform: rotate(2deg); }
.notice-paper:nth-child(4) { background: #c8e6c9; transform: rotate(-1deg); }
.fruit-bowl {
    position: absolute;
    right: 160px; top: 36px;
    width: 24px; height: 16px;
    background: #ff7043;
    border-radius: 0 0 12px 12px;
}
.fruit-bowl::before {
    content: "";
    position: absolute;
    left: 5px; top: -8px;
    width: 9px; height: 9px;
    background: radial-gradient(circle at 35% 35%, #ef5350, #c62828);
    border-radius: 50%;
    box-shadow: inset -1px -1px 2px rgba(0,0,0,0.25);
}
.fruit-bowl::after {
    content: "";
    position: absolute;
    right: 6px; top: -6px;
    width: 11px; height: 7px;
    background: linear-gradient(135deg, #fff176 0 40%, #fdd835 40% 100%);
    border-radius: 50% 50% 50% 50% / 60% 60% 40% 40%;
    box-shadow: inset -1px -1px 2px rgba(0,0,0,0.2);
}
.clock {
    position: absolute;
    right: 32px; bottom: 12px;
    width: 18px; height: 18px;
    background: #fff;
    border: 2px solid #5d4037;
    border-radius: 50%;
}
.clock::after {
    content: "";
    position: absolute;
    left: 50%; top: 4px;
    width: 1px; height: 6px;
    background: #5d4037;
    transform-origin: bottom;
}

/* ==================== 休息区 ==================== */
#restarea { left: 735px; top: 300px; width: 375px; height: 470px; background: #efebe9; }
.sofa {
    position: absolute;
    left: 20px; top: 30px;
    width: 120px; height: 55px;
    background: #5d4037;
    border-radius: 14px;
    box-shadow: 4px 4px 0 rgba(0,0,0,0.12);
}
.sofa::before {
    content: "";
    position: absolute;
    left: -10px; top: 10px;
    width: 16px; height: 38px;
    background: #4e342e;
    border-radius: 10px;
}
.sofa::after {
    content: "";
    position: absolute;
    right: -10px; top: 10px;
    width: 16px; height: 38px;
    background: #4e342e;
    border-radius: 10px;
}
.pillow {
    position: absolute;
    left: 22px; top: 12px;
    width: 26px; height: 26px;
    background: #ffab91;
    border-radius: 5px;
}
.coffee-table {
    position: absolute;
    left: 155px; top: 55px;
    width: 55px; height: 35px;
    background: #8d6e63;
    border-radius: 4px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
.coffee-table::before {
    content: "";
    position: absolute;
    left: 8px; top: 6px;
    width: 18px; height: 12px;
    background: #fff;
    border-radius: 0 0 8px 8px;
}
.coffee-table::after {
    content: "";
    position: absolute;
    right: 8px; top: 5px;
    width: 14px; height: 10px;
    background: linear-gradient(180deg, #fff 0 60%, transparent 60%);
    border: 1px solid #8d6e63;
    border-radius: 2px;
    box-shadow: 1px 1px 0 rgba(0,0,0,0.15);
}
.fish-tank {
    position: absolute;
    right: 18px; bottom: 18px;
    width: 80px; height: 50px;
    background: linear-gradient(180deg, #b3e5fc 0%, #4fc3f7 100%);
    border: 3px solid #6d4c41;
    border-radius: 4px;
    overflow: hidden;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
.fish {
    position: absolute;
    top: 24px; left: 10px;
    width: 20px; height: 11px;
    background: #ff7043;
    border-radius: 50% 50% 40% 40%;
    animation: swim 7s ease-in-out infinite alternate;
}
.fish::after {
    content: "";
    position: absolute;
    right: -5px; top: 2px;
    width: 0; height: 0;
    border-top: 3px solid transparent;
    border-bottom: 3px solid transparent;
    border-left: 7px solid #ff7043;
}
.ripple {
    position: absolute;
    width: 34px; height: 8px;
    border: 1px solid rgba(255,255,255,0.5);
    border-radius: 50%;
    animation: waterRipple 2.2s ease-in-out infinite;
}
.ripple:nth-child(2) { top: 10px; left: 30px; animation-delay: 0.5s; }
.ripple:nth-child(3) { top: 36px; left: 55px; animation-delay: 1s; }
.floor-lamp {
    position: absolute;
    right: 135px; top: 14px;
    width: 8px; height: 75px;
    background: #5d4037;
}
.floor-lamp::before {
    content: "";
    position: absolute;
    left: -14px; top: -10px;
    width: 36px; height: 22px;
    background: #fff9c4;
    border-radius: 10px 10px 0 0;
    box-shadow: 0 0 28px #fff59d;
    animation: flicker 4s ease-in-out infinite;
}
.dream-wall {
    position: absolute;
    left: 220px; top: 12px;
    width: 55px; height: 40px;
    background: #d7ccc8;
    border: 2px solid #6d4c41;
    border-radius: 2px;
    display: flex;
    flex-wrap: wrap;
    align-content: flex-start;
    padding: 3px;
    gap: 3px;
}
.dream-photo {
    width: 12px; height: 14px;
    background: #fff;
    border: 1px solid #8d6e63;
}
.dream-photo:nth-child(1) { background: #c8e6c9; }
.dream-photo:nth-child(2) { background: #fff9c4; }
.dream-photo:nth-child(3) { background: #ffccbc; }
.dream-photo:nth-child(4) { background: #b3e5fc; }

.footer-tip {
    text-align: center;
    padding: 16px;
    color: #6a8a6b;
    font-size: 12px;
}

.rug {
    position: absolute;
    left: 50%; top: 50%;
    transform: translate(-50%, -50%);
    width: 85%; height: 85%;
    background: repeating-linear-gradient(
        45deg,
        rgba(93,64,55,0.06) 0 10px,
        transparent 10px 20px
    );
    border-radius: 8px;
    pointer-events: none;
}

.door {
    position: absolute;
    width: 32px; height: 6px;
    background: #6d4c41;
    border-radius: 3px;
}
.door::after {
    content: "";
    position: absolute;
    right: 4px; top: -2px;
    width: 4px; height: 4px;
    background: #ffd54f;
    border-radius: 50%;
}

.cabinet {
    position: absolute;
    width: 45px; height: 55px;
    background: #8d6e63;
    border-radius: 3px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.1);
}
.cabinet::before {
    content: "";
    position: absolute;
    left: 5px; top: 5px; right: 5px; bottom: 5px;
    border: 1px solid rgba(0,0,0,0.1);
}
.cabinet::after {
    content: "";
    position: absolute;
    left: 50%; top: 8px; bottom: 8px;
    width: 1px;
    background: rgba(0,0,0,0.15);
}
</style>
</head>
<body>
<div class="floorplan-wrapper">
    <div class="floorplan">
        <!-- 阳光 -->
        <div class="window-light" style="top:-80px;right:80px;"></div>
        <div class="window-light" style="top:-80px;left:60px;animation-delay:3s;"></div>

        <!-- 资料库 -->
        <div class="room" id="library">
            <div class="room-label" style="left:15px;top:12px;">资料库</div>
            
            <!-- 三面书墙 -->
            <div class="book-wall book-wall-left">
                <div class="books" style="top:8px;left:4px;right:4px;">
                    <div class="book-spine" style="background:#8d6e63;"></div>
                    <div class="book-spine" style="background:#5d4037;"></div>
                    <div class="book-spine" style="background:#a1887f;"></div>
                    <div class="book-spine" style="background:#4e342e;"></div>
                    <div class="book-spine" style="background:#bcaaa4;"></div>
                    <div class="book-spine" style="background:#6d4c41;"></div>
                    <div class="book-spine" style="background:#795548;"></div>
                    <div class="book-spine" style="background:#8d6e63;"></div>
                    <div class="book-spine" style="background:#5d4037;"></div>
                </div>
            </div>
            <div class="book-wall book-wall-back">
                <div class="books" style="top:6px;left:4px;right:4px;flex-direction:row;gap:3px;">
                    <div class="book-spine" style="width:10px;height:100%;background:#ef5350;"></div>
                    <div class="book-spine" style="width:8px;height:100%;background:#ec407a;"></div>
                    <div class="book-spine" style="width:12px;height:100%;background:#ab47bc;"></div>
                    <div class="book-spine" style="width:9px;height:100%;background:#7e57c2;"></div>
                    <div class="book-spine" style="width:11px;height:100%;background:#5c6bc0;"></div>
                    <div class="book-spine" style="width:8px;height:100%;background:#42a5f5;"></div>
                    <div class="book-spine" style="width:10px;height:100%;background:#26c6da;"></div>
                    <div class="book-spine" style="width:9px;height:100%;background:#66bb6a;"></div>
                </div>
            </div>
            <div class="book-wall book-wall-right">
                <div class="books" style="top:8px;left:4px;right:4px;">
                    <div class="book-spine" style="background:#6d4c41;"></div>
                    <div class="book-spine" style="background:#8d6e63;"></div>
                    <div class="book-spine" style="background:#5d4037;"></div>
                    <div class="book-spine" style="background:#a1887f;"></div>
                    <div class="book-spine" style="background:#4e342e;"></div>
                    <div class="book-spine" style="background:#bcaaa4;"></div>
                </div>
            </div>
            
            <!-- 分类标签（已按需求移除文字） -->
            
            <!-- 阅读桌 -->
            <div class="reading-table">
                <div class="open-book"></div>
                <div class="glasses"></div>
                <div class="globe"></div>
                <div class="cup" style="right:8px;bottom:10px;">
                    <div class="steam"></div>
                    <div class="steam"></div>
                    <div class="steam"></div>
                </div>
            </div>
            
            <!-- 梯子 -->
            <div class="ladder"></div>
            
            <!-- 知识树挂画 -->
            <div class="knowledge-tree"></div>
            
            <!-- 盆栽 -->
            <div class="pot-plant" style="left:80px;bottom:8px;"></div>
            <div class="pot-plant" style="right:8px;bottom:8px;animation-delay:1s;"></div>
            
            <div class="room-char" style="left:150px;top:135px;">
                <img class="desk-photo" src="/sprites/raven.png?v=2" alt="黑卷鸦">
                <div class="room-char-cap">黑卷鸦<br><span>记忆管理员 · 在岗</span></div>
            </div>
            <div class="door" style="right:20px;bottom:2px;"></div>
        </div>

        <!-- 总经理办公室 -->
        <div class="room" id="ceo">
            <div class="room-label" style="left:15px;top:12px;">总经理办公室</div>
            <div class="deer-badge"><img src="/sprites/deer.png?v=2" alt="忧郁鹿"></div>
            <div class="window"></div>
            <div class="bookshelf-small">
                <div class="trophy"></div>
            </div>
            <div class="strategy-board"></div>
            <div class="ceo-desk"></div>
            <div class="ceo-chair"></div>
            <div class="pot-plant" style="left:180px;bottom:12px;"></div>
            <div class="door" style="left:20px;bottom:2px;"></div>
        </div>

        <!-- 调度室 -->
        <div class="room" id="dispatch">
            <div class="room-label" style="left:15px;top:12px;">调度室</div>

            <!-- 墙上排期看板 -->
            <div class="dispatch-board">
                <div class="task-strip" style="left:6px;top:9px;width:42px;background:#66bb6a;"></div>
                <div class="task-strip" style="left:22px;top:20px;width:54px;background:#ffa726;"></div>
                <div class="task-strip" style="left:12px;top:32px;width:50px;background:#42a5f5;"></div>
            </div>

            <!-- 世界地图（统筹全局） -->
            <div class="world-pin"></div>

            <!-- 指挥工位 -->
            <div class="dispatch-desk">
                <div class="dispatch-screen main"></div>
                <div class="dispatch-screen side"></div>
                <div class="dispatch-keyboard"></div>
                <div class="dispatch-chair"></div>
                <div class="cup" style="right:8px;bottom:6px;">
                    <div class="steam"></div>
                    <div class="steam"></div>
                </div>
            </div>

            <!-- 调度工程师 -->
            <div class="room-char" style="left:113px;top:30px;">
                <img class="desk-photo" src="/sprites/kite.png?v=2" alt="天瞰鸢">
                <div class="room-char-cap">天瞰鸢<br><span>调度工程师 · 在岗</span></div>
            </div>
            <div class="door" style="right:20px;bottom:2px;"></div>
        </div>

        <!-- 开放办公区 -->
        <div class="room" id="office-area">
            <div class="room-label" style="left:15px;top:12px;">开放办公区</div>
            <div class="rug"></div>
"""
    )

    # 工位布局（开放办公区 8 个坐班工位，2 行 × 4 列，等距书桌风格）
    # 注：黑卷鸦(记忆管理员)常驻资料库、天瞰鸢(调度工程师)在调度室、忧郁鹿(总经理)在总经理办公室，均不在本区
    positions = [
        (50, 34, "squirrel", "机灵鼠", "idle", "工程师", 3, ["🎧", "🖼️", "📝"], "代码如松鼠囤松果，严谨到每个分号。"),
        (200, 34, "butterfly", "绘羽蝶", "idle", "设计师", 2, ["🎨", "🌸", "📝"], "把冰冷界面雕成会呼吸的翅膀。"),
        (350, 34, "fox", "赤谋狐", "idle", "测试工程师", 3, ["🧪", "🔍", "📝"], "专挑别人忘测的角落下嘴。"),
        (500, 34, "hedgehog", "针客猬", "idle", "安全工程师", 4, ["🔒", "🛡️", "📝"], "浑身是刺，漏洞扎手就缩。"),
        (50, 188, "beaver", "大坝狸", "idle", "运维工程师", 2, ["🔧", "📦", "🖼️"], "把烂摊子筑成稳如大坝的流水线。"),
        (200, 188, "hare", "霜耳兔", "idle", "数据分析师", 2, ["📊", "📈", "🖼️"], "数字里跑最快，异常先一步察觉。"),
        (350, 188, "badger", "土工獾", "idle", "网络工程师", 3, ["🔌", "🌐", "📝"], "地下打洞接管线，接口从不断。"),
        (500, 188, "lark", "清音雀", "idle", "监控工程师", 2, ["🔔", "📟", "🖼️"], "清晨第一声啼，告警从不漏。"),
    ]
    STATUS_TEXT = {"online": "在线", "busy": "忙碌", "idle": "空闲"}
    ACCENT = {
        "squirrel": "#a87238", "butterfly": "#e8a8c8", "fox": "#e87048",
        "hedgehog": "#8a7a5a", "beaver": "#9a6840", "hare": "#c9b6e0",
        "badger": "#8a7a6a", "lark": "#7fb0d8",
    }
    for (x, y, aid, name, st, role, level, items, blurb) in positions:
        accent = ACCENT.get(aid, "#1e6fff")
        stext = STATUS_TEXT.get(st, st)
        desk_svg = f'''<svg class="desk-svg" viewBox="0 0 160 128" xmlns="http://www.w3.org/2000/svg">
      <ellipse cx="80" cy="106" rx="66" ry="13" fill="rgba(15,23,42,0.08)"/>
      <path d="M80,82 L146,100 L80,118 L14,100 Z" fill="{accent}" fill-opacity="0.14"/>
      <path d="M14,100 L80,118 L146,100 L146,106 L80,124 L14,106 Z" fill="{accent}" fill-opacity="0.22"/>
      <path d="M80,90 L114,102 L80,114 L46,102 Z" fill="#e2e8f0"/>
      <path d="M46,102 L80,114 L114,102 L114,108 L80,120 L46,108 Z" fill="#cbd5e1"/>
      <image href="/sprites/{aid}.png?v=2" x="52" y="36" width="56" height="56" preserveAspectRatio="xMidYMid meet"/>
      <path d="M80,88 L142,106 L80,124 L18,106 Z" fill="#f8fafc"/>
      <path d="M18,106 L80,124 L142,106 L142,112 L80,130 L18,112 Z" fill="#e8edf3"/>
      <rect x="18" y="106" width="5" height="18" fill="#cbd5e1"/>
      <rect x="137" y="106" width="5" height="18" fill="#cbd5e1"/>
      <rect x="78" y="124" width="5" height="14" fill="#cbd5e1"/>
      <rect x="66" y="62" width="28" height="22" rx="2" fill="#0f172a"/>
      <rect x="69" y="65" width="22" height="16" rx="1" fill="#1e293b"/>
      <rect x="78" y="84" width="4" height="6" fill="#475569"/>
      <circle class="lamp {st}" cx="128" cy="110" r="4"/>
    </svg>'''
        html += f"""
            <div class="emp-card {st}" style="left:{x}px;top:{y}px;">
                <div class="desk-stage">{desk_svg}</div>
                <div class="ename">{name}</div>
                <div class="erole">{role}</div>
            </div>
"""

    html += (
        """
        </div>

        <!-- 茶水间 -->
        <div class="room" id="breakroom">
            <div class="room-label" style="left:15px;top:12px;">茶水间</div>
            <div class="counter">
                <div class="coffee-machine"></div>
                <div class="microwave"></div>
                <div class="water-dispenser"></div>
                <div class="cup" style="right:12px;bottom:14px;">
                    <div class="steam"></div>
                    <div class="steam"></div>
                </div>
            </div>
            <div class="stool" style="left:42px;top:82px;"></div>
            <div class="stool" style="left:92px;top:82px;"></div>
            <div class="stool" style="left:142px;top:82px;"></div>
            <div class="fruit-bowl"></div>
            <div class="clock"></div>
            <div class="cabinet" style="left:200px;top:15px;"></div>
            <div class="notice-board">
                <div class="notice-paper"></div>
                <div class="notice-paper"></div>
                <div class="notice-paper"></div>
                <div class="notice-paper"></div>
            </div>
        </div>

        <!-- 休息区（放大） -->
        <div class="room" id="restarea">
            <div class="room-label" style="left:15px;top:12px;">休息区</div>
            <div class="dream-wall" style="left:15px;top:42px;"></div>
            <div class="fish-tank" style="right:18px;top:30px;"></div>
            <div class="floor-lamp" style="right:140px;top:22px;"></div>
            <div class="sofa" style="left:20px;top:390px;width:220px;height:70px;">
                <div class="pillow"></div>
                <div class="pillow" style="left:55px;background:#c5e1a5;"></div>
                <div class="pillow" style="left:88px;background:#b3e5fc;"></div>
            </div>
            <div class="coffee-table" style="left:262px;top:410px;"></div>
            <div class="pot-plant" style="left:12px;bottom:8px;"></div>
        </div>

        <!-- 墙体分隔 -->
        <div class="wall wall-h" style="left:30px;top:290px;width:700px;"></div>
        <div class="wall wall-v" style="left:730px;top:300px;height:470px;"></div>
        <div class="wall wall-h" style="left:30px;top:640px;width:360px;"></div>
        <div class="wall wall-v" style="left:300px;top:30px;height:260px;"></div>
        <div class="wall wall-v" style="right:420px;top:30px;height:260px;"></div>
    </div>

</div>

<!-- 信息面板（已移除弹窗） -->
</body>
</html>"""
    )
    return html


@router.get("/vector", response_class=HTMLResponse)
async def vector_page(request: Request) -> str:
    return await asyncio.to_thread(
        lambda: open("static/vector.html", "r", encoding="utf-8").read()
    )


@router.get("/debug", response_class=HTMLResponse)
async def debug_page(request: Request) -> str:
    """调试面板：火焰图 + 推理链路可视化。"""
    traces = debugger.summary()
    trace_options = ""
    for s in traces:
        tid = s.trace_id
        dur = f"{s.total_duration_ms:.1f}" if s.total_duration_ms else "?"
        label = f"{tid[:12]}… ({s.span_count} spans, {dur}ms)"
        trace_options += f'<option value="{tid}">{label}</option>'

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>BlueDeer · 调试面板</title>
<link rel="stylesheet" href="/static/debug.css">
</head>
<body>
<div class="debug-header">
    <div>
        <h1>🔬 BlueDeer 调试面板</h1>
        <div class="subtitle">火焰图 · 推理链路 · Trace 分析</div>
    </div>
    <div class="nav-links">
        <a href="/">🏠 仪表盘</a>
        <a href="/debug" style="border-color:var(--accent-dim);background:rgba(76,175,80,0.1);">🔬 调试面板</a>
    </div>
</div>

<div class="container">
    {f'''<!-- Trace 选择器 -->
    <div class="card trace-selector">
        <label for="traceSelect">选择 Trace:</label>
        <select id="traceSelect">{trace_options}</select>
        <button class="btn btn-sm" id="refreshBtn" style="margin-left:12px;">⟳ 刷新</button>
        <button class="btn btn-sm btn-primary" id="genSampleBtn" style="margin-left:8px;">🎲 生成测试 Trace</button>
    </div>''' if trace_options else '''<div class="card" style="text-align:center;padding:40px;">
        <p style="color:var(--text-secondary);font-size:14px;margin-bottom:16px;">暂无 trace 数据</p>
        <button class="btn btn-primary" id="genSampleBtn">🎲 生成测试 Trace</button>
    </div>'''}

    <!-- Tab 栏 -->
    <div class="tab-bar">
        <button class="tab-btn active" data-tab="flame">
            🔥 火焰图 <span class="badge">Flame Graph</span>
        </button>
        <button class="tab-btn" data-tab="chain">
            🔗 推理链路 <span class="badge">Chain</span>
        </button>
        <button class="tab-btn" data-tab="summary">
            📊 摘要统计 <span class="badge">Summary</span>
        </button>
    </div>

    <!-- 火焰图面板 -->
    <div class="tab-panel active" id="tabFlame">
        <div class="card">
            <h2>🔥 火焰图</h2>
            <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                色块宽度 = 耗时 · 悬停查看详情 · 点击色块放大 · 点击空白恢复
            </p>
            <div class="legend" id="flameLegend">
                <div class="legend-item"><span class="legend-color" style="background:hsla(140,55%,40%,0.8)"></span>Agent</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(210,60%,40%,0.8)"></span>Tool</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(30,70%,42%,0.8)"></span>Model</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(280,45%,40%,0.8)"></span>Event</div>
                <div class="legend-item"><span class="legend-color" style="background:hsla(0,70%,45%,0.8)"></span>Error</div>
            </div>
            <div class="flame-container">
                <canvas id="flameCanvas"></canvas>
                <div class="flame-tooltip" id="flameTooltip"></div>
            </div>
        </div>
    </div>

    <!-- 推理链路面板 -->
    <div class="tab-panel" id="tabChain">
        <div class="card">
            <h2>🔗 Agent 调用链</h2>
            <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                树形结构，显示 Agent 调用顺序和耗时
            </p>
            <div id="chainTreeContainer"></div>
        </div>
        <div class="card">
            <h2>📐 Mermaid 流程图</h2>
            <p style="font-size:12px;color:var(--text-secondary);margin-bottom:12px;">
                从 Canvas 模块生成的调用流程图
            </p>
            <div class="mermaid-container" id="mermaidContainer">
                <pre id="mermaidCode" style="font-size:12px;color:var(--text-secondary);overflow-x:auto;"></pre>
            </div>
        </div>
    </div>

    <!-- 摘要统计面板 -->
    <div class="tab-panel" id="tabSummary">
        <div id="summaryContent">
            <div class="card" style="text-align:center;padding:40px;">
                <p style="color:var(--text-secondary);font-size:13px;">选择 trace 查看统计</p>
            </div>
        </div>
    </div>
</div>

<script src="/static/debug.js"></script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8080)
