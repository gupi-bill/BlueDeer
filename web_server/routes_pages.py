# 自动拆分自 web_server.py（路由域: pages）
import logging

logger = logging.getLogger(__name__)
from fastapi import APIRouter

from web_server.app import (
    app,
    debugger,
    scene,
)

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request) -> str:
    """2.5D 平面图仪表盘页面。"""
    status = scene.status()
    offices_data = scene.office_manager.to_dict()
    github_data = github.stats()
    scene.breakroom.recent(count=5, msg_type=None)

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
    background: #0d1a12;
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

.header {
    background: linear-gradient(135deg,#1b3a1e,#2e5a35);
    padding: 18px 30px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    border-bottom: 2px solid #4caf50;
    position: sticky;
    top: 0;
    z-index: 1000;
}
.header h1 { font-size: 24px; color: #e8f5e9; letter-spacing: 2px; }
.header .subtitle { font-size: 12px; color: #a5d6a7; margin-top: 4px; }
.header .stats-mini {
    display: flex;
    gap: 20px;
    font-size: 12px;
}
.header .stats-mini span { color: #c8e6c9; }
.header .stats-mini b { color: #81c784; margin-right: 4px; }

.floorplan-wrapper {
    padding: 30px;
    min-width: 1200px;
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
.room-icon {
    font-size: 22px;
    margin-right: 6px;
}

/* ==================== 资料库 Library ==================== */
#library { left: 30px; top: 30px; width: 260px; height: 240px; background: #efebe9; }

/* 三面书墙 */
.book-wall {
    position: absolute;
    background: #5d4037;
    border-radius: 3px;
    box-shadow: 3px 3px 0 rgba(0,0,0,0.12);
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
    border-radius: 1px;
    border-left: 3px solid rgba(255,255,255,0.3);
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
#ceo .window {
    position: absolute;
    right: 0; top: 25px;
    width: 16px; height: 150px;
    background: linear-gradient(180deg, #b3e5fc, #81d4fa);
    border-left: 3px solid #5d4037;
}
#ceo .window::before {
    content: "🌲";
    position: absolute;
    right: 4px; top: 25px;
    font-size: 16px;
    opacity: 0.7;
}
#ceo .window::after {
    content: "☁️";
    position: absolute;
    right: 2px; top: 60px;
    font-size: 12px;
    opacity: 0.6;
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

/* ==================== 开放办公区 ==================== */
#office-area { left: 30px; top: 300px; width: 700px; height: 320px; background: #d7ccc8; }
.desk {
    position: absolute;
    width: 120px; height: 85px;
    background: #a1887f;
    border-radius: 4px;
    box-shadow: 4px 4px 0 rgba(0,0,0,0.12);
    cursor: pointer;
    transition: transform 0.2s;
}
.desk:hover { transform: translateY(-3px); z-index: 50; }
.desk-top {
    position: absolute;
    left: 8px; top: -10px;
    width: 104px; height: 55px;
    background: #8d6e63;
    border-radius: 3px;
}
.monitor {
    position: absolute;
    left: 22px; top: -40px;
    width: 55px; height: 35px;
    background: #263238;
    border-radius: 3px;
    border: 2px solid #455a64;
    overflow: hidden;
    animation: screenGlow 3s ease-in-out infinite;
}
.monitor::after {
    content: "</>";
    position: absolute;
    left: 10px; top: 9px;
    font-size: 11px;
    color: #69f0ae;
    font-family: monospace;
}
.keyboard {
    position: absolute;
    left: 20px; top: 12px;
    width: 60px; height: 15px;
    background: #5d4037;
    border-radius: 2px;
}
.mouse {
    position: absolute;
    right: 14px; top: 14px;
    width: 11px; height: 15px;
    background: #5d4037;
    border-radius: 50%;
}
.cup {
    position: absolute;
    right: 12px; bottom: 12px;
    width: 13px; height: 15px;
    background: #fff;
    border-radius: 0 0 6px 6px;
    border: 1px solid #d7ccc8;
}
.cup::before {
    content: "";
    position: absolute;
    right: -5px; top: 2px;
    width: 6px; height: 8px;
    border: 2px solid #fff;
    border-radius: 0 6px 6px 0;
    border-left: none;
}
.steam {
    position: absolute;
    right: 14px; bottom: 26px;
    width: 6px; height: 10px;
    background: rgba(255,255,255,0.6);
    border-radius: 50%;
    animation: floatSteam 2.5s ease-out infinite;
}
.steam:nth-child(2) { animation-delay: 0.6s; }
.steam:nth-child(3) { animation-delay: 1.2s; }
.plant {
    position: absolute;
    left: 10px; bottom: 8px;
    width: 18px; height: 26px;
    font-size: 20px;
    line-height: 1;
}
.chair {
    position: absolute;
    width: 38px; height: 38px;
    background: #5d4037;
    border-radius: 50%;
    box-shadow: 2px 2px 0 rgba(0,0,0,0.12);
}
.employee-name {
    position: absolute;
    left: 50%;
    bottom: -22px;
    transform: translateX(-50%);
    font-size: 11px;
    color: #3e2723;
    font-weight: 700;
    white-space: nowrap;
    text-shadow: 0 1px 0 rgba(255,255,255,0.5);
}
.status-dot {
    position: absolute;
    right: 6px; top: -55px;
    width: 8px; height: 8px;
    background: #4caf50;
    border-radius: 50%;
    animation: statusPulse 2s ease-in-out infinite;
}
.status-dot.busy { background: #ff9100; }
.status-dot.idle { background: #9e9e9e; }
.headphones {
    position: absolute;
    left: 8px; top: -6px;
    font-size: 16px;
}
.phone {
    position: absolute;
    right: 32px; top: 18px;
    width: 10px; height: 16px;
    background: #37474f;
    border-radius: 2px;
}
.sticky-note {
    position: absolute;
    right: 2px; top: -32px;
    width: 14px; height: 14px;
    background: #fff59d;
    border-radius: 1px;
    transform: rotate(8deg);
    box-shadow: 1px 1px 2px rgba(0,0,0,0.1);
}
.photo-frame {
    position: absolute;
    left: 4px; top: -34px;
    width: 14px; height: 16px;
    background: #6d4c41;
    border-radius: 1px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 9px;
}

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
    content: "🍎";
    position: absolute;
    left: 3px; top: -10px;
    font-size: 12px;
}
.fruit-bowl::after {
    content: "🍌";
    position: absolute;
    right: 2px; top: -8px;
    font-size: 10px;
}
.clock {
    position: absolute;
    right: 160px; top: 10px;
    width: 20px; height: 20px;
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
#restarea { right: 30px; top: 650px; width: 360px; height: 120px; background: #efebe9; }
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
    content: "📓";
    position: absolute;
    right: 6px; top: 4px;
    font-size: 12px;
}
.fish-tank {
    position: absolute;
    right: 22px; top: 22px;
    width: 95px; height: 58px;
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

/* 信息面板 */
.info-panel {
    position: fixed;
    right: 30px;
    top: 110px;
    width: 320px;
    background: rgba(13,26,18,0.95);
    border: 1px solid #4caf50;
    border-radius: 12px;
    padding: 20px;
    box-shadow: 0 10px 40px rgba(0,0,0,0.5);
    backdrop-filter: blur(10px);
    z-index: 2000;
    max-height: calc(100vh - 140px);
    overflow-y: auto;
}
.info-panel h3 {
    color: #81c784;
    font-size: 16px;
    margin-bottom: 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #2e7d32;
}
.info-panel p, .info-panel li {
    font-size: 13px;
    color: #c8e6c9;
    line-height: 1.7;
}
.info-panel ul { padding-left: 18px; margin: 8px 0; }
.info-panel .close-btn {
    position: absolute;
    right: 12px; top: 12px;
    width: 24px; height: 24px;
    background: #2e7d32;
    border: none;
    border-radius: 50%;
    color: #fff;
    cursor: pointer;
    font-size: 14px;
}
.info-panel .close-btn:hover { background: #4caf50; }

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
<div class="header">
    <div>
        <h1>🦌 BlueDeer 森林公司</h1>
        <div class="subtitle">2.5D 平面户型图 · 点击房间查看详情</div>
    </div>
    <div class="stats-mini">
        <span><b>"""
        + str(status["library"]["total_entries"])
        + """</b>资料库</span>
        <span><b>"""
        + str(status["breakroom"]["total_messages"])
        + """</b>茶水间</span>
        <span><b>"""
        + str(status["offices"]["total_offices"])
        + """</b>办公室</span>
        <span><b>"""
        + str(github_data["total_projects"])
        + """</b>GitHub项目</span>
    </div>
</div>

<div class="floorplan-wrapper">
    <div class="floorplan">
        <!-- 阳光 -->
        <div class="window-light" style="top:-80px;right:80px;"></div>
        <div class="window-light" style="top:-80px;left:60px;animation-delay:3s;"></div>

        <!-- 资料库 -->
        <div class="room" id="library" onclick="showRoom('library')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">📚</span>资料库</div>
            
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
            
            <!-- 分类标签 -->
            <div class="shelf-label" style="left:20px;top:42px;">架构</div>
            <div class="shelf-label" style="left:20px;top:80px;">算法</div>
            <div class="shelf-label" style="left:20px;top:118px;">GitHub</div>
            <div class="shelf-label" style="left:80px;top:42px;">最佳实践</div>
            
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
            <div class="knowledge-tree">🌳</div>
            
            <!-- 盆栽 -->
            <div class="pot-plant" style="left:80px;bottom:8px;">🪴</div>
            <div class="pot-plant" style="right:8px;bottom:8px;animation-delay:1s;">🌿</div>
            
            <div class="door" style="right:20px;bottom:2px;"></div>
        </div>

        <!-- 总经理办公室 -->
        <div class="room" id="ceo" onclick="showRoom('ceo')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">🫎</span>总经理办公室</div>
            <div class="deer-badge">🦌</div>
            <div class="window"></div>
            <div class="bookshelf-small">
                <div class="trophy">🏆</div>
            </div>
            <div class="strategy-board">📈</div>
            <div class="ceo-desk"></div>
            <div class="ceo-chair"></div>
            <div class="pot-plant" style="left:180px;bottom:12px;">🌵</div>
            <div class="door" style="left:20px;bottom:2px;"></div>
        </div>

        <!-- 开放办公区 -->
        <div class="room" id="office-area" onclick="showRoom('office')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">🏢</span>开放办公区</div>
            <div class="rug"></div>
"""
    )

    # 工位布局
    positions = [
        (60, 60, "squirrel", "较真松鼠", "online"),
        (210, 60, "hedgehog", "戒备猬", "busy"),
        (360, 60, "owl", "夜枭猫头鹰", "online"),
        (510, 60, "beaver", "勤恳海狸", "idle"),
        (130, 200, "fox", "狡黠狐狸", "online"),
        (340, 200, "desk6", "待招岗位", "idle"),
    ]
    personal_items = [
        ["🎧", "🖼️", "📝"],
        ["🔒", "🖼️", ""],
        ["🧠", "🖼️", "📝"],
        ["🔧", "🖼️", ""],
        ["🧪", "🖼️", "📝"],
        ["", "", ""],
    ]
    for idx, (x, y, aid, name, st) in enumerate(positions):
        office_info = offices_data.get("offices", {}).get(aid, {})
        badge = office_info.get("badge", {})
        level = badge.get("level", 1)
        role = badge.get("role", "")
        status_class = f"status-dot {st}"
        items = personal_items[idx]
        headphone = f'<div class="headphones">{items[0]}</div>' if items[0] else ""
        photo = f'<div class="photo-frame">{items[1]}</div>' if items[1] else ""
        sticky = '<div class="sticky-note"></div>' if items[2] else ""
        click_attr = (
            f"onclick=\"event.stopPropagation();showDesk('{aid}','{name}','{role}',{level})\""
            if aid != "desk6"
            else ""
        )
        html += f"""
            <div class="desk" style="left:{x}px;top:{y}px;" {click_attr}>
                <div class="desk-top"></div>
                <div class="monitor"></div>
                {photo}
                {sticky}
                <div class="keyboard"></div>
                <div class="mouse"></div>
                <div class="phone"></div>
                <div class="cup"><div class="steam"></div><div class="steam"></div><div class="steam"></div></div>
                {headphone}
                <div class="plant">🪴</div>
                <div class="chair" style="bottom:-32px;left:38px;"></div>
                <div class="{status_class}"></div>
                <div class="employee-name">{name}</div>
            </div>
"""

    html += (
        """
        </div>

        <!-- 茶水间 -->
        <div class="room" id="breakroom" onclick="showRoom('breakroom')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">☕</span>茶水间</div>
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

        <!-- 休息区 -->
        <div class="room" id="restarea" onclick="showRoom('restarea')">
            <div class="room-label" style="left:15px;top:12px;"><span class="room-icon">🧘</span>休息区</div>
            <div class="sofa">
                <div class="pillow"></div>
                <div class="pillow" style="left:55px;background:#c5e1a5;"></div>
                <div class="pillow" style="left:88px;background:#b3e5fc;"></div>
            </div>
            <div class="coffee-table"></div>
            <div class="floor-lamp"></div>
            <div class="dream-wall">
                <div class="dream-photo"></div>
                <div class="dream-photo"></div>
                <div class="dream-photo"></div>
                <div class="dream-photo"></div>
                <div class="dream-photo" style="width:100%;height:10px;background:#e1bee7;"></div>
            </div>
            <div class="fish-tank">
                <div class="ripple"></div>
                <div class="ripple"></div>
                <div class="ripple"></div>
                <div class="fish"></div>
            </div>
            <div class="pot-plant" style="left:12px;bottom:8px;">🌿</div>
        </div>

        <!-- 墙体分隔 -->
        <div class="wall wall-h" style="left:30px;top:290px;width:700px;"></div>
        <div class="wall wall-h" style="left:30px;top:640px;width:360px;"></div>
        <div class="wall wall-h" style="right:30px;top:640px;width:360px;"></div>
        <div class="wall wall-v" style="left:300px;top:30px;height:260px;"></div>
        <div class="wall wall-v" style="right:420px;top:30px;height:260px;"></div>
    </div>
</div>

<!-- 信息面板 -->
<div class="info-panel" id="infoPanel">
    <button class="close-btn" onclick="closePanel()">×</button>
    <h3>🏢 欢迎来到 BlueDeer 森林公司</h3>
    <p>点击任意房间或员工工位查看详情。</p>
    <ul>
        <li>📚 资料库：三面书墙、彩色书脊、阅读桌、地球仪、知识树挂画</li>
        <li>🫎 总经理办公室：忧郁鹿全局调度中心</li>
        <li>🏢 开放办公区：6 个独立工位，每个都有独特个人物品</li>
        <li>☕ 茶水间：咖啡机、微波炉、饮水机、水果、公告板</li>
        <li>🧘 休息区：沙发、落地灯、鱼缸、梦境照片墙</li>
    </ul>
</div>

<div class="footer-tip">
    BlueDeer 森林公司 · 多智能体协同办公系统 · 认知架构 v2.5D+
</div>

<script>
const roomData = {
    library: {
        title: "📚 资料库",
        content: "公司拥有三面书墙，收录 <b>"""
        + str(status["library"]["total_entries"])
        + """</b> 条知识条目，整合 <b>"""
        + str(github_data["total_projects"])
        + """</b> 个 GitHub 精选项目。阅读桌上摊开的书、地球仪、眼镜和热茶，知识的香气扑面而来。"
    },
    ceo: {
        title: "🫎 总经理办公室",
        content: "忧郁鹿的调度中心。负责任务分发、负载均衡、熔断重分配、Token 审计与奖惩结算。窗外就是森林，墙上挂着战略图。"
    },
    office: {
        title: "🏢 开放办公区",
        content: "6 个独立工位，员工状态实时显示。绿点在线、橙点忙碌、灰点空闲。每个工位都有显示器、键盘、热茶杯、绿植和独特的个人物品。"
    },
    breakroom: {
        title: "☕ 茶水间",
        content: "员工自由交流区。当前有 <b>"""
        + str(status["breakroom"]["total_messages"])
        + """</b> 条消息。咖啡机、微波炉、饮水机一应俱全，公告板贴着最新通知。"
    },
    restarea: {
        title: "🧘 休息区",
        content: "放松与梦境回放空间。舒适的沙发、落地灯、游着金鱼的鱼缸，还有记录成功与失败记忆的梦境照片墙。"
    }
};

function showRoom(room) {
    const panel = document.getElementById('infoPanel');
    const data = roomData[room];
    panel.innerHTML = '<button class="close-btn" onclick="closePanel()">×</button><h3>' + data.title + '</h3><p>' + data.content + '</p>';
    panel.style.display = 'block';
}

function showDesk(aid, name, role, level) {
    const panel = document.getElementById('infoPanel');
    panel.innerHTML = '<button class="close-btn" onclick="closePanel()">×</button>' +
        '<h3>🧑‍💻 ' + name + '</h3>' +
        '<p><b>岗位：</b>' + (role || '工程师') + '</p>' +
        '<p><b>等级：</b>Lv' + level + '</p>' +
        '<p><b>工号：</b>' + aid + '</p>' +
        '<p>正在使用高性能工作站，显示器上运行着代码。桌上一杯热茶正冒着袅袅热气。</p>';
    panel.style.display = 'block';
}

function closePanel() {
    document.getElementById('infoPanel').style.display = 'none';
}
</script>
</body>
</html>"""
    )
    return html


@router.get("/vector", response_class=HTMLResponse)
async def vector_page(request: Request) -> str:
    with open("static/vector.html", "r", encoding="utf-8") as f:
        return f.read()


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
