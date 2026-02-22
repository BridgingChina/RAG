# 智谱 ZIP 下载解析 — 修复 PDF 入库失败

## 问题

Ingest task #4（PDF 入库）失败，报 `No chunks generated from parsed content`。
根因：智谱文件解析 API 在 `download_link` 模式下 `content=None`，解析结果在 zip 包里。
`_download_and_store_parsed_assets` 是 `pass` 占位，`parsed_content` 为空。

## 实测 ZIP 结构

```
result.zip (2966 bytes)
├── result.md   (4399 bytes, Markdown 内容)
└── images/     (空目录, PDF 无图时为空; Expert 模式含图片)
```

- Expert 模式：images + Markdown
- Prime 模式：images + Markdown + layout JSON
- download_url 24 小时有效

## 方案

下载 zip → 存档到 R2 → 提取 markdown → 提取图片存档。

### `_parse_pdf` 流程变更

```
poll_until_done(download_link)
  ├─ download_url 存在 → _download_and_store_parsed_assets → 返回 parsed_md
  ├─ content 存在（fallback） → parsed_md = content
  └─ 都没有 → raise ValueError
```

### `_download_and_store_parsed_assets` 实现

```
httpx GET download_url → zip_bytes
  ├─ R2 上传 parsed/{task.id}/archive.zip（原始存档）
  ├─ zipfile 内存解压
  │   ├─ 找 *.md → 读取 → parsed_md
  │   └─ 遍历 images/* → 逐个上传 R2 parsed/{task.id}/images/{name}
  └─ 返回 parsed_md (str)
```

方法签名从 `-> None` 改为 `-> str`。

### R2 存储结构

```
parsed/{task.id}/
  ├── result.md       (已有, _parse_pdf 末尾上传)
  ├── archive.zip     (新增, 原始 zip 存档)
  └── images/         (新增, 提取的图片)
```

### 图片 URL 策略

Markdown 中图片路径保持原样（相对路径）。图片仅存档，不改写 URL，不在前端渲染。

### 错误处理

| 场景 | 处理 |
|------|------|
| zip 下载失败 | httpx 异常，上层 `_fail()` 捕获 |
| zip 中无 .md 文件 | raise ValueError |
| .md 内容为空 | 返回空串，后续 `_chunk()` 报错 |
| 无 images 目录或图片 | 跳过，不报错 |
| 多个 .md 文件 | 取第一个 |

## 改动范围

| 文件 | 变更 |
|------|------|
| `app/services/ingest_task_service.py` | 实现 `_download_and_store_parsed_assets`（~25 行），修改 `_parse_pdf` 赋值逻辑（3 行） |

无新增依赖、无 schema 变更、无前端改动。
