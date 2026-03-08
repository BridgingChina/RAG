# Chunk 拆分交互重做设计

## 问题

当前拆分交互：点"拆分" → 弹窗 → 输入字符索引数字 → 确认。用户需要心算字符位置，没有预览，体验极差。

## 方案

替换弹窗为 **拆分模式**（原地替换右侧编辑区），提供两种选择方式 + 双面板预览。

### 状态机

```
正常编辑 ──点击"拆分"──→ selecting（选择阶段）
                           ├ paragraph（段落模式 A）
                           └ precise（精确模式 C）
                               │ 选中分割点
                               ↓
                          previewing（预览阶段）
                           ├ 重选 → 回到 selecting
                           ├ 取消 → 回到正常编辑
                           └ 确认 → 调 API → onMutated()
```

状态：
- `splitPhase: null | 'selecting' | 'previewing'`
- `splitSubMode: 'paragraph' | 'precise'`
- `splitPosition: number | null`

拆分模式下隐藏正常编辑区（textarea、表单字段、保存/删除按钮）。

### 段落模式 (A) — SplitParagraphView

内容按 `\n\n` 分段渲染（无 `\n\n` 时 fallback 按 `\n` 分行）。段间显示分割线：

- 默认态：浅灰虚线 + ✂ 图标 + 左右字数
- Hover 态：蓝色高亮，上方段落加浅蓝底、下方段落加浅绿底
- 点击 → 设置 splitPosition → 进入 previewing

边界：单行内容（无 `\n\n` 也无 `\n`）→ 段落模式禁用，默认进精确模式。空段落合并为一个分割点。

### 精确模式 (C) — SplitPreciseView

只读 textarea + 底部状态栏：

- Textarea `readOnly`，用户点击定位光标
- 监听 `onSelect` 实时更新状态栏：光标位置、两半字数
- "在此拆分"按钮（光标在首/末时禁用）→ 设置 splitPosition → 进入 previewing

Textarea 设为只读防止用户在拆分模式下改内容导致 position 偏移。

### 模式切换

selecting 阶段顶部显示两个 Button tab（`variant="default"` 激活 / `variant="outline"` 未激活）。切换时不重置已选的 splitPosition。

### 预览阶段 — SplitPreview

两个面板（Chunk A 浅蓝底 / Chunk B 浅绿底）平分可用高度：

- 外层 `flex flex-col h-full`，面板各 `flex-1 min-h-0 overflow-y-auto`
- 面板标题：`Chunk A/B` + 字数统计
- 文本 `font-mono text-sm whitespace-pre-wrap`
- 底部：取消 + 确认拆分（复用现有 splitting state + ConflictError 处理）
- 顶部："重选位置"按钮 → 回到 selecting

不做：预览阶段微调 position、预测 search_text/contextual_text、显示继承的 metadata。

## 变更范围

**只改一个文件：** `web/src/pages/ChunkEditorPage.tsx`

新增内部组件：
- `SplitModeHeader` — 标题 + 模式切换 + 取消
- `SplitParagraphView` — 段落分割线视图
- `SplitPreciseView` — 只读 textarea + 状态栏
- `SplitPreview` — 双面板预览 + 确认

删除：`splitDialogOpen`/`splitPos` state、`openSplitDialog()`、Split Dialog JSX。

修改：`handleSplit()` 参数改用 `splitPosition`；拆分按钮 onClick 改为进入 selecting。

**后端零改动。**
