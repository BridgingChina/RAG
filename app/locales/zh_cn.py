# 中文简体消息字典。flat key, dot notation。
# 占位符语法：{name}（Python str.format）。
# 新增 key 时必须同步 en_us.py，否则 en-US 请求会 fallback 到这里（有 warning 日志）。

MESSAGES: dict[str, str] = {
    # ── bridges
    "bridges.not_found": "桥梁不存在",
    "bridges.exists": "桥梁「{name}」已存在",
    "bridges.invalid_id": "桥梁 ID 格式错误",
    # ── chunks
    "chunks.not_found": "Chunk 不存在",
    "chunks.conflict": "Chunk 已被其他人修改，请刷新后重试",
    # ── knowledge
    "knowledge.point_not_found": "知识点不存在",
    "knowledge.no_evidence": "未找到相关证据",
    # ── auth
    "auth.invalid_token": "认证失败，请重新登录",
    "auth.forbidden": "无权限执行此操作",
    # ── qa
    "qa.no_evidence": "未找到相关证据",
    "qa.degraded_chinese_fallback": "（英文回答生成失败，降级为中文）",
    # ── translation / i18n
    "translation.pending": "正在翻译",
    "translation.fallback_notice": "（译文缺失，展示中文原文）",
    # ── ingest
    "ingest.task_not_found": "入库任务不存在",
    "ingest.upload_failed": "文件上传失败",
    # ── generic
    "error.internal": "服务内部错误",
    "error.rate_limited": "请求过于频繁，请稍后再试",
    "error.validation": "请求参数错误",
}
