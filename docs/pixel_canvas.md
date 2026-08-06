# PixelCanvas 像素画布使用指南

## 1. 快速开始

```python
from core.pixel_canvas import PixelCanvas, Color

canvas = PixelCanvas(width=80, height=24)

# 画像素
canvas.set_pixel(10, 5, "@", Color.GREEN)

# 画矩形
canvas.draw_rect(5, 5, 20, 10, char="#", color=Color.BLUE, fill=True)

# 画文本
canvas.draw_text(10, 15, "Hello BlueDeer", color=Color.YELLOW)

# 居中文本
canvas.draw_text_centered(20, "Centered", color=Color.CYAN)

# 渲染
output = canvas.render()
print(output)
```

## 2. 颜色

使用 ANSI 256 色码，支持高饱和和企业级低饱和色板：

| 颜色 | 色码 | 说明 |
|------|------|------|
| `Color.BLACK` | 0 | 黑色 |
| `Color.WHITE` | 255 | 白色 |
| `Color.RED` | 196 | 红色（高饱和） |
| `Color.SOFT_RED` | 167 | 柔红（低饱和） |
| `Color.GREEN` | 46 | 绿色（高饱和） |
| `Color.SAGE` | 108 | 灰绿（低饱和） |
| `Color.YELLOW` | 226 | 黄色（高饱和） |
| `Color.AMBER` | 179 | 琥珀（低饱和） |
| `Color.CYAN` | 51 | 青色（高饱和） |
| `Color.STEEL_BLUE` | 67 | 钢蓝（低饱和） |

## 3. 绘图操作

### 3.1 像素

```python
canvas.set_pixel(x, y, char, color=Color.WHITE, layer=None)
pixel = canvas.get_pixel(x, y)
```

### 3.2 矩形

```python
# 填充矩形
canvas.draw_rect(x, y, w, h, char="#", color=Color.WHITE, fill=True)

# 边框矩形
canvas.draw_rect(x, y, w, h, char="#", color=Color.WHITE, fill=False)
```

### 3.3 文本

```python
# 左对齐文本
canvas.draw_text(x, y, "Hello", color=Color.WHITE)

# 居中文本
canvas.draw_text_centered(y, "Hello", color=Color.WHITE)
```

### 3.4 精灵

```python
sprite = [
    "  @@  ",
    " @@@@ ",
    "  @@  ",
]
color_map = {"@": Color.GREEN}
canvas.draw_sprite(x, y, sprite, color_map)
```

### 3.5 边框

```python
canvas.draw_border(x, y, w, h, color=Color.GRAY)
```

## 4. 图层管理

```python
# 添加图层
canvas.add_layer("overlay")

# 在指定图层绘图
canvas.set_pixel(10, 5, "@", Color.RED, layer="overlay")

# 获取图层
layer_data = canvas.get_layer("base")

# 撤销图层操作
canvas.undo_layer("overlay")
```

## 5. 撤销/重做

```python
# 撤销指定图层
canvas.undo_layer("base")
```

## 6. 渲染

```python
# 渲染为 ANSI 着色字符串（终端显示）
output = canvas.render()

# 渲染为纯文本（无颜色）
plain = canvas.render_plain()
```

## 7. 清空画布

```python
canvas.clear()  # 清空所有图层
```

## 8. 注意事项

- 越界坐标自动裁剪，不会抛出异常
- 空字符不绘制
- 图层默认名为 `base`
- 撤销历史最多保留 50 步
