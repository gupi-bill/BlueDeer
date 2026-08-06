# RAG 向量检索调优指南

## 1. 知识库分层

RAGSystem 管理三层知识库：

| 层级 | 说明 | 示例 |
|------|------|------|
| `global` | 全局公共库 | 项目规范、开发规范、角色档案 |
| `agent` | 岗位私有库 | 各员工历史任务方案、代码模板 |
| `task` | 临时任务库 | 单次任务临时素材（任务完成后清理） |

## 2. 数据注入

```python
rag = RAGSystem(db_root="data/db")

# 注入全局知识
rag.ingest("global", "coding-standard", "代码必须使用类型注解...")

# 注入岗位知识
rag.ingest("agent", "fox-profile", "Fox 擅长 Python 开发...", sub_id="fox")

# 注入临时知识（不持久化）
rag.ingest("task", "task-123-notes", "本次任务特殊要求...", sub_id="task-123", persist=False)
```

## 3. 检索模式

### 3.1 单层检索

```python
results = rag.retrieve("Python 类型注解", scope="global", top_k=3)
```

### 3.2 跨层检索

```python
results = rag.retrieve_cross(
    "Python 类型注解",
    scopes=[("global", ""), ("agent", "fox")],
    top_k=3,
)
```

### 3.3 多路召回融合

```python
results = rag.retrieve_multi_source(
    "Python 类型注解",
    scopes=[("global", ""), ("agent", "fox")],
    top_k=3,
    use_vector=True,
    use_keyword=True,
    use_kg=False,
    ensemble_weights=(0.5, 0.3, 0.2),  # 向量、关键词、知识图谱
)
```

## 4. 融合权重调优

`ensemble_weights` 控制三种召回源的权重：

| 场景 | 推荐权重 (向量, 关键词, 知识图谱) |
|------|----------------------------------|
| 通用检索 | (0.5, 0.3, 0.2) |
| 精确匹配 | (0.3, 0.6, 0.1) |
| 概念探索 | (0.6, 0.2, 0.2) |

## 5. 置信度过滤

```python
results = rag.retrieve(
    "Python 类型注解",
    scope="global",
    top_k=5,
    confidence_threshold=0.3,  # 只返回 >= 0.3 的结果
)
```

置信度标签：
- `high`：score >= 0.6
- `medium`：0.3 <= score < 0.6
- `low`：score < 0.3

## 6. 性能优化建议

### 6.1 向量检索优化
- 引入近似最近邻（ANN）索引（如 FAISS、HNSW）
- 对高频查询结果缓存

### 6.2 关键词检索优化
- 当前使用正则分词，可替换为 BM25 算法
- 建立倒排索引加速关键词匹配

### 6.3 分层检索优化
- 优先检索最相关层，避免全层扫描
- 对冷门层延迟加载

## 7. 注意事项

- 检索失败不会阻塞主链路，返回空列表并记录错误日志
- 临时任务库（task 层）建议定期清理
- 知识库持久化路径由 `config.db_root` 控制
