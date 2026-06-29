# V4.0 Deep System Defect List

> **审计类型**: deep_sys（深层系统审计 — Store/View逻辑 + Pipeline安全）
> **审计日期**: 2026-06-25
> **审计范围**: 前端 Zustand Store / React Components / 后端 Django SSE Pipeline / RAG Pipeline
> **审计原则**: 完全只读，不修改任何代码
> **溯源规则**: 所有引用使用 `[来源: V3.x/文件名.md §章节]` 格式

---

## 严重度分类标准

| 级别 | 标签 | 判定条件 | 上线要求 |
|------|------|----------|----------|
| CRITICAL | P0 | 数据泄露 / 成本爆炸 / 系统崩溃 / 认证绕过 | **上线前必须修复** |
| HIGH | P1 | 已认证用户可利用的安全漏洞 / 数据污染竞态 / >5×性能退化 / >10×成本风险 | 下一个版本必须修复 |
| MEDIUM | P2 | 信息泄露 / UX不一致 / 缺失安全机制 / 2-5×边界性能退化 / 不破坏数据的行为错误 | 建议下版本修复 |
| LOW | P3 | 代码质量 / 开发残留 / 类型安全 / UX小修 / 未激活路径的潜在缺陷 | 方便时修复 |

---

## CRITICAL (P0)

### DEFECT-001: SSE endpoint 绕过 DRF throttle classes — 成本爆炸风险

- **严重度**: CRITICAL
- **类别**: Security (Cost Control)
- **位置**: `backend/apps/chat/views.py:123-125`
- **影响**: `/api/v1/chat/sessions/{id}/send/` 是系统最昂贵的 API（触发 RAG Pipeline + DashScope LLM 调用），但使用 `@api_view(["POST"])` 装饰器，该装饰器不继承 DRF 的 `DEFAULT_THROTTLE_CLASSES`。攻击者可在认证后以无限速率调用此端点，导致 DashScope 按调用计费模型的成本爆炸。3000并发用户场景下，单用户每分钟可发送 >1000 次 RAG 查询，按 DashScope qwen-plus ¥0.004/次 计算，单用户单分钟可产生 ¥4+ 费用。
- **根因**: DRF 的 `DEFAULT_THROTTLE_CLASSES` 仅对继承 `APIView` 的视图生效。`@api_view` 装饰器将函数转为 `APIView` 子类，但不自动应用 `DEFAULT_THROTTLE_CLASSES`。需要显式添加 `@throttle_classes`。
- **溯源**: `[来源: V3.4/bug_list.md §MED-003]` — V3.4 已发现但至今未修复，V4.0 升级为 CRITICAL
- **关联**: DEFECT-011 (CSRF绕过同根因)

**代码证据**:
```python
# views.py:123-125 — 缺少 @throttle_classes
@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def send_message(request, session_id):
```

对比 DRF 配置 (`base.py:146-151`):
```python
"DEFAULT_THROTTLE_CLASSES": [
    "rest_framework.throttling.UserRateThrottle",
],
"DEFAULT_THROTTLE_RATES": {
    "user": "30/minute",
},
```

---

## HIGH (P1)

### DEFECT-002: ReactMarkdown XSS — `a` href 和 `img` src 未校验协议

- **严重度**: HIGH
- **类别**: Security (XSS)
- **位置**: `frontend/src/components/chat/MessageBubble.tsx:12-20` (ALLOWED_ELEMENTS 定义), `313-321` (ReactMarkdown渲染)
- **影响**: ALLOWED_ELEMENTS 白名单包含 `a` 和 `img`。自定义 `a` 组件仅添加 `target="_blank"` 和 `rel="noopener noreferrer"`，但**未校验 href 协议**。攻击向量：
  1. `[link](javascript:alert(1))` — `javascript:` 协议可通过 `<a>` 标签执行
  2. `[img](data:image/svg+xml,<svg onload=alert(1)>)` — `data:` URI 可嵌入恶意 SVG
  3. `unwrapDisallowed={true}` 使被禁止元素的子文本保留在 DOM 中（虽不执行，但表明内容未经消毒）
- **根因**: 未使用 DOMPurify 或任何 HTML 消毒库。ReactMarkdown 内部的 rehype-sanitize 未被启用（未配置 `sanitize` 选项）。自定义 components 仅做了 UX 增强（`target="_blank"`），未做安全过滤。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-003 (localStorage JWT — XSS可窃取令牌放大此缺陷)

**代码证据**:
```tsx
// MessageBubble.tsx:12-20 — 白名单包含 a 和 img
const ALLOWED_ELEMENTS = [
  'p', 'br', 'strong', 'em', 'u', 's', 'del', 'ins', 'sub', 'sup',
  'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
  'ul', 'ol', 'li',
  'blockquote', 'code', 'pre', 'hr',
  'table', 'thead', 'tbody', 'tr', 'th', 'td',
  'a', 'img',   // ← 未校验协议
  'details', 'summary',
];

// MessageBubble.tsx:313-317 — a 组件无 href 校验
a: ({ href, children }) => (
  <a href={href} target="_blank" rel="noopener noreferrer">  // ← href 直接透传
    {children}
  </a>
),
```

### DEFECT-003: localStorage JWT — XSS 可窃取令牌实现账户接管

- **严重度**: HIGH
- **类别**: Security (Authentication)
- **位置**: `frontend/src/auth/AuthProvider.tsx:30-46`, `frontend/src/api/client.ts:11-23`
- **影响**: JWT 令牌以 JSON 格式存储在 `localStorage`（键名 `ey-auth`）。任何 XSS 攻击（包括 DEFECT-002）可通过 `localStorage.getItem('ey-auth')` 提取 JWT，实现完整账户接管。OWASP ASVS 明确禁止在 localStorage 存储 sensitive tokens。
- **根因**: 登录流程 (`AuthProvider.tsx:45`) 直接将含 JWT 的完整 AuthState 写入 localStorage。401拦截器 (`client.ts:30-33`) 仅做清除+重定向，无令牌刷新。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-002 (XSS是窃取JWT的前提), DEFECT-009 (JWT过期无刷新同根因)

**代码证据**:
```ts
// AuthProvider.tsx:44-45 — JWT 写入 localStorage
const newState: AuthState = { isAuthenticated: true, user, token };
setState(newState);
localStorage.setItem('ey-auth', JSON.stringify(newState));

// client.ts:13-17 — 从 localStorage 读取 JWT
const saved = localStorage.getItem('ey-auth');
if (saved) {
  const { token } = JSON.parse(saved);
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
}
```

### DEFECT-004: retriever.py raw SQL filter_key 字符串拼接 — SQL注入风险

- **严重度**: HIGH
- **类别**: Security (SQL Injection)
- **位置**: `backend/apps/rag/retriever.py:138-142`
- **影响**: `_search_pgvector` 方法中，`filters` dict 的 key 直接用于 SQL WHERE 子句拼接：`f"{key} = %s"`。虽然 value 通过参数化查询安全传递，但 key 未校验。若 `filters` dict 的 key 来自用户输入（当前来自代码内部，暂无直接攻击面），攻击者可注入 `1=1 OR` 等恶意 SQL 片段。
- **根因**: 过度信任 filters dict 的 key 来源。当前调用路径 (`views.py -> pipeline.py -> retriever.py`) 不传 filters，所以 key 始终为空。但作为库级 API，此接口设计不安全。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-013 (SSE错误泄露内部信息)

**代码证据**:
```python
# retriever.py:138-142 — key 直接拼接
if filters:
    filter_parts = []
    for key, value in filters.items():
        filter_parts.append(f"{key} = %s")   # ← key 未校验，直接拼入SQL
        filter_params.append(value)
    filter_sql = " AND " + " AND ".join(filter_parts)
```

### DEFECT-005: RAGPipeline 每请求新建实例 — 6个对象/请求浪费

- **严重度**: HIGH
- **类别**: Performance (Resource Waste)
- **位置**: `backend/apps/chat/views.py:170`, `backend/apps/rag/pipeline.py:20-31`
- **影响**: `send_message` 函数内每次 SSE 请求创建 `RAGPipeline()` 新实例。`RAGPipeline.__init__` 创建 6 个子对象：`DocumentParser`(SSE路径从不使用)、`LangChainChunker`、`EmbeddingService`、`PgVectorRetriever`、`PromptBuilder`、`GuardrailsService` + `LiteLLMChatService`。3000并发场景下，每秒产生 ~50 个 RAGPipeline 实例（按 30/min throttle 标准速率），累积 ~300 个无用对象，加重 GC 压力。
- **根因**: `RAGPipeline` 无模块级单例。LiteLLMChatService 和 EmbeddingService 已有单例模式（`get_llm_service()` / `get_shared_httpx_client()`），但 RAGPipeline 本身未复用。特别是 `DocumentParser` 仅在 Celery ingest 路径使用，SSE 路径完全浪费。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-022 (DocumentParser无用创建), DEFECT-015 (call_with_safety绕过singleton)

**代码证据**:
```python
# views.py:170 — 每请求新建
from apps.rag.pipeline import RAGPipeline
pipeline = RAGPipeline()  # ← 每次SSE请求都新建

# pipeline.py:20-31 — __init__ 创建6个子对象
class RAGPipeline:
    def __init__(self):
        self.parser = DocumentParser()       # ← SSE路径从不使用
        self.chunker = LangChainChunker(...)  # ← SSE路径从不使用
        self.embedder = EmbeddingService()    # ← 有全局缓存但仍有实例开销
        self.retriever = PgVectorRetriever()  # ← 无单例
        self.prompt_builder = PromptBuilder() # ← 纯模板对象可复用
        self.guardrails = GuardrailsService() # ← 无单例
        self.llm = LiteLLMChatService()       # ← __init__调用get_shared_httpx_client()
```

---

## MEDIUM (P2)

### DEFECT-006: StreamLifecycleManager TOCTOU — JS单线程下实际安全，但架构耦合风险

- **严重度**: MEDIUM
- **类别**: Race Condition (Architectural Risk)
- **位置**: `frontend/src/stream/StreamLifecycleManager.ts:22-30`
- **影响**: `createStreamAbortController(sessionId)` 在同一函数内先调用 `abortActiveStream()` 再赋新值。在 JS 单线程模型下，这两步不会交错，因此**实际不会产生竞态**。但真正风险在于架构耦合：Zustand 状态（`streamPhase`、`isSendLocked`）与模块级单例变量（`activeAbortController`、`activeStreamSessionId`）混合管理，违反单一状态源原则，增加维护难度。
- **根因**: AbortController 不可序列化，无法存入 Zustand，因此采用模块级变量。这是合理的工程权衡，但应在文档中明确声明非 Zustand 管理的状态。
- **溯源**: `[来源: V3.4/bug_list.md §CRIT-001]` + `[来源: V3.5/reports/综合审计报告.md §streamPhase修复]`
- **关联**: DEFECT-008 (跨Tab无法同步模块级变量)

### DEFECT-007: SSE 无断连重连机制 — 网络中断丢失流式响应

- **严重度**: MEDIUM
- **类别**: Reliability (Disconnect Recovery)
- **位置**: `frontend/src/store/chatStore.ts:378-544` (sendMessage SSE 逻辑)
- **影响**: 当 SSE 连接因网络中断断开时，前端仅做 2次重试（1s/2s延迟），失败后显示错误 banner。若断开发生在流式响应中间（已收到部分 tokens），`streamContent` 在错误处理中被清空，用户**丢失已接收的所有部分响应**。后端也可能已保存完整响应到 DB（取决于断开时机），但前端无法恢复。
- **根因**: SSE 是单向协议，无内置重连/续传机制。前端 `reader.read()` 抛出异常后，`catch` 块仅做 retry 或 error display，无 partial recovery 逻辑。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-009 (JWT过期也导致中断)

### DEFECT-008: 无 BroadcastChannel 跨 Tab 同步 — 多标签页状态冲突

- **严重度**: MEDIUM
- **类别**: Reliability (Cross-Tab Consistency)
- **位置**: (架构缺失 — 无特定文件)
- **影响**: 多个浏览器标签页共享同一 localStorage JWT，但各自有独立的 Zustand store 和 StreamLifecycleManager 单例。Tab A 发送消息时，Tab B 的 `abortActiveStream()` 仅影响 Tab B，不会中断 Tab A 的流。若 Tab B 删除了 Tab A 正在使用的 session，Tab A 的 SSE 连接继续运行，但后端 session 已标记 `is_active=False`，导致不一致。
- **根因**: 无跨 Tab 通信机制。每个 JS 上下文有独立模块级变量。
- **溯源**: `[来源: V3.8/综合审计报告_V3.8.md §未来改进]` — V3.8 已列为未来改进项
- **关联**: DEFECT-006 (模块级变量跨Tab不共享)

### DEFECT-009: JWT 15分钟过期无刷新 — 长对话强制登出

- **严重度**: MEDIUM
- **类别**: Reliability (Authentication Continuity)
- **位置**: `frontend/src/api/client.ts:26-35`, `backend/config/settings/base.py:159-163`
- **影响**: JWT access token 有效期仅 15分钟（`JWT_ACCESS_TOKEN_LIFETIME_MINUTES=15`）。前端仅存储 access token，无 refresh token。401拦截器 (`client.ts:30-33`) 直接清除 localStorage + 重定向 `/login`。意味着用户在长对话中（>15min）被强制登出，SSE 流中断，丢失上下文。
- **根因**: SIMPLE_JWT 配置了 `ROTATE_REFRESH_TOKENS=True` 和 `BLACKLIST_AFTER_ROTATION=True`，后端支持 refresh token，但前端从未使用 refresh token。AuthProvider (`AuthProvider.tsx:42-45`) 的 login 仅保存 `{ token, user }`，无 refresh 字段。
- **溯源**: `[来源: V3.8/综合审计报告_V3.8.md §未来改进]` — V3.8 已列为未来改进项
- **关联**: DEFECT-003 (JWT存储方式), DEFECT-007 (中断类型)

### DEFECT-010: Guardrails regex 可被 Unicode 同形字和多语言绕过

- **严重度**: MEDIUM
- **类别**: Security (Prompt Injection)
- **位置**: `backend/apps/rag/guardrails.py:23-47`
- **影响**: INJECTION_PATTERNS 全部使用 ASCII 正则 (`(?i)` 仅匹配 ASCII 字母大小写)。攻击向量：
  1. **Unicode 同形字攻击**: `ⅰgnore` (U+2170 小罗马数字I) 替代 `ignore`，`Ꭾretend` (U+13AE Cherokee) 替代 `pretend`，正则不匹配
  2. **多语言绕过**: 中文提示注入如 "忽略之前的规则" 不被任何正则捕获（`(?i)ignore` 不匹配 "忽略"）
  3. **编码混淆**: Base64编码的指令如 "aWdub3JlIGFsbCBpbnN0cnVjdGlvbnM=" (="ignore all instructions") 不被捕获
- **根因**: 正则仅覆盖英文攻击模式。EY Onboarding AI 支持中英双语，但 guardrails 仅保护英文注入路径。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-002 (AI输出XSS可被注入触发)

### DEFECT-011: SSE endpoint 无 CSRF 保护

- **严重度**: MEDIUM
- **类别**: Security (CSRF)
- **位置**: `backend/apps/chat/views.py:123`
- **影响**: `@api_view(["POST"])` 绕过 Django `CsrfViewMiddleware`。当前使用 header-based JWT 认证（浏览器不会自动发送 Authorization header），因此 CSRF 风险较低。但如果未来 JWT 迁移到 httpOnly cookie（DEFECT-003修复方案），浏览器会自动发送 cookie，CSRF 攻击成为可能。
- **根因**: `@api_view` 创建的视图类不经过 `CsrfViewMiddleware`。DRF 对使用 JWT 认证的视图自动免除 CSRF，但无显式声明。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-001 (同根因: @api_view绕过), DEFECT-003 (JWT→cookie迁移后CSRF变真实威胁)

### DEFECT-012: custom_exception_handler 泄露 str(exc) — 内部信息暴露

- **严重度**: MEDIUM
- **类别**: Security (Information Disclosure)
- **位置**: `backend/apps/core/exceptions.py:14`
- **影响**: 500错误响应包含 `"detail": str(exc)`，可能泄露数据库连接字符串、API key片段、文件路径等内部信息。
- **根因**: DRF 默认 exception_handler 对未捕获异常返回 None，custom handler 填充 `str(exc)` 到响应体。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-013 (SSE路径同样泄露)

**代码证据**:
```python
# exceptions.py:14 — 500响应泄露异常详情
return Response(
    {"error": "Internal server error", "detail": str(exc)},  # ← str(exc)可能含敏感信息
    status=status.HTTP_500_INTERNAL_SERVER_ERROR,
)
```

### DEFECT-013: event_stream SSE 泄露 str(e) — 流式路径信息暴露

- **严重度**: MEDIUM
- **类别**: Security (Information Disclosure)
- **位置**: `backend/apps/chat/views.py:210-211`
- **影响**: SSE `event: error` 事件直接将 `str(e)` 作为 JSON data 发送到前端。与 DEFECT-012 相同的泄露风险，但在 SSE 流式路径中更隐蔽（不经过 exception handler）。
- **根因**: `event_stream()` generator 的 `except Exception as e` 块直接 yield `str(e)`。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-012 (同类型泄露，不同路径)

**代码证据**:
```python
# views.py:210-211 — SSE错误事件泄露异常信息
except Exception as e:
    yield "event: error\n"
    yield f"data: {json.dumps({'error': str(e)}, ensure_ascii=False)}\n\n"  # ← str(e)泄露
```

### DEFECT-014: LiteLLMChatService recreate 后旧引用残留

- **严重度**: MEDIUM
- **类别**: Reliability (Connection Management)
- **位置**: `backend/apps/rag/guardrails.py:153-156`
- **影响**: 当 `httpx.ConnectError` 发生时，`stream_chat()` 调用 `recreate_shared_httpx_client()` 后更新 `self._client`。但其他 `LiteLLMChatService` 实例（如 `call_with_safety` 方法创建的 DEFECT-015 实例）仍持有旧 client 引用。旧 client 在 recreate 函数外关闭（`guardrails.py:163-167`），存在短暂双 client 并存窗口。
- **根因**: `recreate_shared_httpx_client()` 关闭旧 client 是在锁外执行的。`LiteLLMChatService` 实例仅在 `stream_chat()` 方法内更新自身 `_client`，其他实例不受影响。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-015 (call_with_safety绕过singleton创建独立实例)

### DEFECT-015: GuardrailsService.call_with_safety 绕过 LLM singleton

- **严重度**: MEDIUM
- **类别**: Code Quality (Singleton Consistency)
- **位置**: `backend/apps/rag/guardrails.py:69`
- **影响**: `call_with_safety` 方法直接创建 `LiteLLMChatService()` 而非使用 `get_llm_service()` singleton。虽然 `__init__` 内调用 `get_shared_httpx_client()`（共享连接池），但 wrapper 对象每次新建。当前 `RAGPipeline.retrieve_and_generate` 不使用 `call_with_safety`（直接调 `self.guardrails.check_input()` + `self.llm.stream_chat()`），此路径未激活。
- **根因**: `call_with_safety` 是早期遗留接口，`RAGPipeline` 已改用直接调用模式，但旧接口仍存在。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-014 (旧实例持有过期client引用)

### DEFECT-016: generateSmartTitle CJK regex 范围不全

- **严重度**: MEDIUM
- **类别**: Data Integrity (Title Generation)
- **位置**: `frontend/src/store/chatStore.ts:69`
- **影响**: 正则 `/[一-鿿]/.test(title)` 仅覆盖 CJK Unified Ideographs 基本区 (U+4E00-U+9FFF)。不含 Extension A (U+3400-U+4DBF，含常用异体字)、CJK Compatibility Ideographs (U+F900-U+FAFF)。中文商务场景中常见的人名/地名异体字可能被误判为非CJK，导致英文截断策略被错误应用于中文标题。
- **根因**: Unicode 范围选择仅覆盖最常用区段，未考虑扩展区。
- **溯源**: NEW (V4.0首次发现)
- **关联**: 无

**代码证据**:
```ts
// chatStore.ts:69 — CJK范围不全
const isCJK = /[一-鿿]/.test(title);  // ← 仅覆盖U+4E00-U+9FFF，缺Extension A/F等
```

### DEFECT-017: Feedback unique_together 阻止更新 — 用户无法修改反馈

- **严重度**: MEDIUM
- **类别**: UX (Data Model Constraint)
- **位置**: `backend/apps/chat/models.py:123`
- **影响**: `unique_together = ["message"]` 确保每条消息只有一条反馈。用户先 thumbs-down 后想改 thumbs-up，第二次 POST 返回 400 错误。无 PATCH/PUT 更新端点。
- **根因**: 模型设计假设反馈是一次性操作，无考虑修改场景。
- **溯源**: NEW (V4.0首次发现)
- **关联**: 无

### DEFECT-018: send_message 对任意 UUID 自动建 session — 无服务端格式校验

- **严重度**: MEDIUM
- **类别**: Security (Session Validation)
- **位置**: `backend/apps/chat/views.py:135-149`
- **影响**: 当 `session_id` 在当前用户下不存在且全局也不存在时，后端自动创建 `ChatSession.objects.create(id=session_id, user=user, title=content[:50])`。前端做了 UUID 格式校验 (`chatStore.ts:355`)，但后端 URL pattern `<uuid:session_id>` 已约束格式为标准 UUID，所以实际攻击面有限。但设计上应通过 `ChatSessionListCreateView` 创建 session，而非在 send 中隐式创建。
- **根因**: "首次消息自动建 session" 的 UX 方便性导致在 send 端点中混合了 create 逻辑。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-001 (同端点设计问题)

---

## LOW (P3)

### DEFECT-019: console.log 验证日志遗留生产代码

- **严重度**: LOW
- **类别**: Code Quality (Dev Artifacts)
- **位置**: `frontend/src/store/chatStore.ts:230, 240, 588`, `frontend/src/pages/ChatPage.tsx:145`
- **影响**: V3.7 P1.3 添加的 `console.log('[V3.7 P1.3] ...')` 验证日志标注为 "Dev-only: can be removed before production release"，但仍在代码中。生产环境下这些日志暴露内存管理细节和内部状态信息。
- **根因**: V3.7 优化验收期间添加，标记可移除但未实际移除。
- **溯源**: `[来源: V3.7/性能优化验收报告_V3.7.md §P1.3]` — V3.7验收时明确标注为开发调试日志

### DEFECT-020: DateGroupKey type 含 bare string — 失去类型安全

- **严重度**: LOW
- **类别**: Code Quality (Type Safety)
- **位置**: `frontend/src/utils/dateGroup.ts:6` (推测路径)
- **影响**: `DateGroupKey = 'today' | 'yesterday' | '7days' | '30days' | string` 中 `string` 覆盖了所有 literal type，实际等于 `string`，TypeScript 无法对 month-key 格式做类型约束。
- **根因**: 联合类型中 `string` 是 supertype，使 literal types 失效。
- **溯源**: NEW (V4.0首次发现)

### DEFECT-021: formatDate 硬编码 zh-CN locale

- **严重度**: LOW
- **类别**: UX (Internationalization)
- **位置**: `frontend/src/utils/dateGroup.ts:82-87` (推测路径)
- **影响**: `formatDate` 函数始终使用 `zh-CN` locale 格式化日期，不读取用户语言偏好。英文用户看到中文格式日期。
- **根因**: V3.5/V3.6 开发时默认中文语境，未考虑 i18n。
- **溯源**: `[来源: V3.8/综合审计报告_V3.8.md §未来改进]` — V3.8 已列为i18n待改项

### DEFECT-022: DocumentParser 每请求新建但从不使用

- **严重度**: LOW
- **类别**: Code Quality (Dead Code)
- **位置**: `backend/apps/rag/pipeline.py:21`
- **影响**: `RAGPipeline.__init__` 创建 `DocumentParser()` 实例赋给 `self.parser`，但 `retrieve_and_generate` 方法从不调用 `self.parser`。仅在 Celery `ingest_document` 任务的 `pipeline.ingest(doc)` 路径使用。每个 SSE 请求创建一个无用的 `DocumentParser` 对象。
- **根因**: `RAGPipeline` 混合了两个职责（SSE推理 + 文档导入），导致 SSE 路径加载了导入路径的依赖。
- **溯源**: NEW (V4.0首次发现)
- **关联**: DEFECT-005 (RAGPipeline实例化浪费)

---

## 统计汇总

| 严重度 | 数量 | ID列表 |
|--------|------|--------|
| CRITICAL | 1 | 001 |
| HIGH | 4 | 002, 003, 004, 005 |
| MEDIUM | 13 | 006-018 |
| LOW | 4 | 019-022 |
| **总计** | **22** | |

**安全类缺陷**: 001, 002, 003, 004, 010, 011, 012, 013 (8个)
**可靠性类缺陷**: 006, 007, 008, 009, 014 (5个)
**性能类缺陷**: 005, 022 (2个)
**数据完整性类缺陷**: 016, 017, 018 (3个)
**代码质量类缺陷**: 015, 019, 020, 021 (4个)

---

## V3.8 遗留问题状态追踪

| V3.8遗留 | V4.0状态 | DEFECT编号 |
|----------|----------|-----------|
| HistoryPage日期分组不一致 | 未变（HistoryPage不在路由中，属死代码） | 不列入（非深层系统缺陷） |
| 知识库空 — RAG citations 不可验证 | 未变（数据问题非代码缺陷） | 不列入 |
| SSE限流绕过 (V3.4-MED-003) | **升级为 CRITICAL** → DEFECT-001 | `[来源: V3.4/bug_list.md §MED-003]` |
