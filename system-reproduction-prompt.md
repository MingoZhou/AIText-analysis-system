# 策知 - AI 文本分析系统 完整复现提示词

> 本提示词用于从零开始生成一个与"策知 - AI 文本分析系统"完全相同的系统。请按照下述步骤逐步操作，即可完整复现整个系统。

---

请帮我构建一个完整的"策知 - AI 文本分析系统"。这是一个集政策资讯爬虫采集、AI 智能分析、角色权限管理于一体的全栈 Web 应用。请严格按照以下规范，按"后端 → 前端 → 部署"的顺序逐步实现。

---

## 一、系统概览

- **项目名**：策知 - AI 文本分析系统
- **技术栈**：
  - 后端：FastAPI + SQLAlchemy 2.0 (async) + SQLite + httpx + jieba + APScheduler
  - 前端：Vue 3 + Vite 6 + Element Plus + ECharts + Three.js + GSAP + markdown-it + highlight.js
  - 通信：axios（Bearer Token 拦截器）
- **核心功能**：
  1. 政策资讯多源爬虫采集（Bing/Baidu/站内搜索/RSS）
  2. AI 智能分析（摘要、对话、词云、图表）
  3. 角色权限管理（管理员/普通用户、Token 限额）
- **目录结构建议**：
  ```
  AIText-analysis-system/
  ├── backend/
  │   ├── app/
  │   │   ├── main.py
  │   │   ├── config.py
  │   │   ├── database.py
  │   │   ├── models/
  │   │   ├── schemas/
  │   │   ├── routers/
  │   │   ├── services/
  │   │   └── utils/
  │   ├── data/            # SQLite 数据库目录
  │   ├── requirements.txt
  │   └── run.py
  └── frontend/
      ├── src/
      │   ├── views/
      │   ├── components/
      │   ├── router/
      │   ├── api/
      │   ├── stores/
      │   └── assets/
      ├── package.json
      └── vite.config.js
  ```

---

## 二、后端架构（FastAPI）

### 2.1 开发环境与依赖

`backend/requirements.txt` 应包含：
```
fastapi
uvicorn[standard]
sqlalchemy[asyncio]
aiosqlite
httpx
jieba
apscheduler
python-multipart
pydantic[email]
pydantic-settings
```

Python 版本要求：3.10+（使用 async/await、类型注解）。

### 2.2 配置项（config.py）

使用 pydantic-settings 管理配置，关键配置值如下：

| 配置项 | 值 | 说明 |
|--------|-----|------|
| DB 路径 | `data/ai_text.db` | SQLite 数据库文件 |
| 爬虫 UA | `Mozilla/5.0 ... Chrome/120.0.0.0 ...` | 伪装 Chrome 120 |
| 爬虫超时 | 30 秒 | httpx 请求超时 |
| 每关键词最大采集 | 20 条 | 单次采集上限 |
| 限速 | 2s（同域）/ 15s（同源） | 请求间隔 |
| 熔断阈值 | 12 小时 | 连续失败后暂停 |
| 调度器间隔 | 30 分钟 | 检查关键词采集周期 |
| 调度器时区 | Asia/Shanghai | APScheduler 时区 |
| CORS 来源 | `http://localhost:5173`, `http://localhost:3000` | 允许的前端源 |
| SMTP 主机 | `smtp.qq.com:465` | QQ 邮箱 SSL |
| Token 有效期 | 30 天 | 登录会话有效期 |
| 验证码有效期 | 10 分钟 | 邮箱验证码 |
| 密码哈希迭代 | 600,000 次 | PBKDF2-HMAC-SHA256 |
| 默认管理员 | admin | 自动创建，admin_role=1 |

CORS 中间件配置：允许指定 origins、允许 credentials、允许所有方法和头。

### 2.3 数据库初始化（database.py）

- 使用 SQLAlchemy 2.0 async 引擎：`create_async_engine("sqlite+aiosqlite:///data/ai_text.db")`
- AsyncSession 工厂，`async_sessionmaker`
- `get_db()` 异步依赖生成器
- 启动时 `Base.metadata.create_all` 自动建表

### 2.4 数据库迁移策略

**不使用 Alembic**，采用自研轻量迁移方案：

1. 定义 `SQLITE_COLUMNS` 字典，记录每张表应有的列名与类型
2. 启动时用 `PRAGMA table_info(table_name)` 检测现有列
3. 对缺失的列执行 `ALTER TABLE table_name ADD COLUMN col_name TYPE DEFAULT ...`
4. 自动创建默认 admin 用户（admin_role=1，预设密码）
5. 按名称补充缺失的 `DEFAULT_DATA_SOURCES`（内置数据源种子数据）

### 2.5 数据模型（SQLAlchemy 2.0 async, SQLite）

所有模型继承自同一 `Base`（DeclarativeBase）。使用 Mapped/mapped_column 类型注解风格。

#### 2.5.1 User（用户）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| username | String unique | 用户名 |
| password_hash | String | PBKDF2 哈希 |
| display_name | String | 显示名 |
| email | String | 邮箱 |
| phone | String | 电话 |
| avatar | String | 头像路径 |
| email_verified | Boolean default False | 邮箱是否验证 |
| notify_on_crawl | Boolean default True | 采集通知开关 |
| is_active | Boolean default True | 是否启用 |
| admin_role | Integer default 0 | 0 普通 / 1 管理员 |
| created_at | DateTime | 创建时间 |

#### 2.5.2 AuthSession（认证会话）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| token_hash | String | SHA256 哈希后的 token |
| expires_at | DateTime | 过期时间（30 天） |
| last_seen_at | DateTime | 最后活跃时间 |
| created_at | DateTime | 创建时间 |

#### 2.5.3 ProviderPreference（智能体偏好）
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | Integer PK FK→User | 主键+外键 |
| preset_order | JSON | 预设排序数组 |
| current_provider_id | Integer | 当前选用的 provider |

#### 2.5.4 Keyword（关键词策略）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| keyword | String | 关键词 |
| category | String | 分类 |
| is_active | Boolean default True | 是否启用 |
| crawl_interval | Integer | 采集间隔（小时） |
| date_range_days | Integer default 7 | 时间范围（天） |
| aliases | JSON | 别名列表 |
| exact_phrases | JSON | 精确短语 |
| excluded_terms | JSON | 排除词 |
| site_filters | JSON | 站点过滤 |
| source_ids | JSON | 指定数据源 ID |
| notify_on_crawl | Boolean | 采集通知 |
| last_crawl_at | DateTime | 最后采集时间 |
| created_at | DateTime | 创建时间 |

#### 2.5.5 DataSource（数据源）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| name | String | 名称 |
| source_kind | String | official / rss / search |
| base_url | String | 基础 URL |
| domain | String | 域名 |
| priority | Integer default 0 | 优先级 |
| is_active | Boolean default True | 是否启用 |
| config | JSON | 配置（如 RSS 地址、搜索参数） |
| created_at | DateTime | 创建时间 |

#### 2.5.6 Article（文章）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| keyword_id | Integer FK→Keyword | 关键词 |
| title | String | 标题 |
| content | Text | 正文 |
| summary | Text | 摘要 |
| source_url | String | 来源 URL |
| canonical_url | String | 规范化 URL |
| content_hash | String | 内容哈希（去重） |
| source_name | String | 来源名 |
| source_type | String | 来源类型 |
| author | String | 作者 |
| publish_date | DateTime | 发布日期 |
| crawl_date | DateTime | 采集日期 |
| file_path | String | PDF 文件路径 |
| file_type | String | 文件类型 |
| mime_type | String | MIME 类型 |
| file_size | Integer | 文件大小 |
| is_read | Boolean default False | 是否已读 |
| is_starred | Boolean default False | 是否收藏 |
| tags | JSON | 标签 |
| extra_metadata | JSON | 额外元数据 |
| created_at | DateTime | 创建时间 |

#### 2.5.7 ArticleKeyword（文章-关键词多对多）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| article_id | Integer FK→Article | 文章 |
| keyword_id | Integer FK→Keyword | 关键词 |
| matched_query | String | 匹配的查询词 |
| relevance_score | Float | 相关性评分 |

#### 2.5.8 AIProvider（AI 智能体）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| name | String | 名称 |
| provider_key | String | 标识（如 openai/deepseek/qwen/local-ollama） |
| provider_type | String | cloud / local |
| base_url | String | API 地址 |
| api_key | String | 密钥 |
| default_model | String | 默认模型 |
| context_window | Integer | 上下文窗口 |
| is_active | Boolean default True | 是否启用 |
| is_current | Boolean default False | 是否当前选用 |
| extra_config | JSON | 额外配置 |
| created_at | DateTime | 创建时间 |

#### 2.5.9 AnalysisResult（分析结果）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| analysis_type | String | summary / chat / chart / wordcloud |
| provider_id | Integer FK→AIProvider | 智能体 |
| model | String | 模型名 |
| prompt | Text | 提示词 |
| result | JSON | 结果数据 |
| created_at | DateTime | 创建时间 |

#### 2.5.10 CrawlLog（采集日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| keyword_id | Integer FK→Keyword | 关键词 |
| status | String | running / success / failed / partial |
| query_plan | JSON | 查询计划 |
| found_count | Integer default 0 | 发现数 |
| fetched_count | Integer default 0 | 抓取数 |
| parsed_count | Integer default 0 | 解析数 |
| saved_count | Integer default 0 | 保存数 |
| duplicate_count | Integer default 0 | 重复数 |
| rejected_count | Integer default 0 | 拒绝数 |
| failed_count | Integer default 0 | 失败数 |
| error_message | Text | 错误信息 |
| started_at | DateTime | 开始时间 |
| finished_at | DateTime | 完成时间 |

#### 2.5.11 CrawlItem（采集明细）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| crawl_log_id | Integer FK→CrawlLog | 日志 |
| article_id | Integer FK→Article nullable | 关联文章 |
| title | String | 标题 |
| url | String | URL |
| status | String | success / failed / skipped |
| stage | String | discovery / fetch / parse / dedup / save |
| http_status | Integer | HTTP 状态码 |
| error_message | Text | 错误信息 |
| created_at | DateTime | 创建时间 |

#### 2.5.12 ChatSession（对话会话）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| title | String | 会话标题 |
| keyword_id | Integer FK→Keyword nullable | 关联关键词 |
| model | String | 模型 |
| memory_summary | Text | 记忆摘要 |
| context_compressed | Boolean default False | 是否已压缩 |
| is_active | Boolean default True | 是否活跃 |
| created_at | DateTime | 创建时间 |
| updated_at | DateTime | 更新时间 |

#### 2.5.13 ChatMessage（对话消息）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| session_id | Integer FK→ChatSession | 会话 |
| role | String | user / assistant / system |
| content | Text | 内容 |
| token_count | Integer default 0 | Token 数 |
| created_at | DateTime | 创建时间 |

#### 2.5.14 Role（角色）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| name | String unique | 角色名 |
| description | String | 描述 |
| daily_token_limit | Integer default 100000 | 每日 Token 限额 |
| monthly_token_limit | Integer default 3000000 | 每月 Token 限额 |
| created_at | DateTime | 创建时间 |

#### 2.5.15 UserRole（用户-角色多对多）
| 字段 | 类型 | 说明 |
|------|------|------|
| user_id | Integer FK→User | 用户 |
| role_id | Integer FK→Role | 角色 |
（联合主键 user_id + role_id）

#### 2.5.16 ProviderGrant（智能体授权）
| 字段 | 类型 | 说明 |
|------|------|------|
| provider_id | Integer FK→AIProvider | 智能体 |
| role_id | Integer FK→Role | 角色 |
（联合主键 provider_id + role_id）

#### 2.5.17 TokenUsageLog（Token 用量日志）
| 字段 | 类型 | 说明 |
|------|------|------|
| id | Integer PK | 主键 |
| user_id | Integer FK→User | 用户 |
| provider_id | Integer FK→AIProvider | 智能体 |
| analysis_type | String | 分析类型 |
| prompt_tokens | Integer | 输入 Token |
| completion_tokens | Integer | 输出 Token |
| total_tokens | Integer | 总 Token |
| created_at | DateTime | 创建时间 |

### 2.6 服务层（services/）

#### 2.6.1 auth_service.py — 认证服务
- **密码哈希**：PBKDF2-HMAC-SHA256，迭代 600,000 次，盐值随机 16 字节，存储格式 `pbkdf2_sha256$iterations$salt$hash`
- **Token 会话**：生成随机不透明 Token（secrets.token_urlsafe），数据库存储 SHA256 哈希值，有效期 30 天
- **get_current_user 依赖**：从 Authorization Bearer 头解析 token，哈希后查 AuthSession，校验过期时间，更新 last_seen_at，返回 User
- **注册流程**：校验用户名唯一 → 验证邮箱验证码（10 分钟有效）→ 哈希密码 → 创建用户
- **登录流程**：校验密码 → 创建 AuthSession → 返回 token

#### 2.6.2 permission_service.py — 权限服务
- **管理员判断**：`user.admin_role == 1`
- **角色权限检查**：查询用户关联的 UserRole，判断是否被授权使用某 provider（ProviderGrant）
- **Token 限额管理**：
  - 管理员不限额（直接放行）
  - 普通用户：汇总当日/当月 TokenUsageLog，对比角色 daily_token_limit / monthly_token_limit
  - 超限则拒绝并返回明确错误
- **智能体可见性**：管理员可见全部 provider；普通用户仅可见被授权的 provider

#### 2.6.3 ai_service.py — AI 智能分析服务
- **OpenAI 兼容 API**：统一使用 `/v1/chat/completions` 接口格式，httpx 异步请求
- **摘要生成**：将文章标题+正文拼入 prompt，调用 AI 生成结构化摘要
- **对话（带 RAG）**：
  - 根据用户消息检索相关文章（关键词匹配）
  - 将检索结果作为上下文注入
  - 携带历史消息（受 context_window 限制）
  - 超过窗口时触发记忆压缩（摘要历史）
- **17 个云端预设** + **3 个本地预设**：
  - 云端：OpenAI、DeepSeek、通义千问(Qwen)、智谱(GLM)、Moonshot(Kimi)、百川、零一(01.AI)、MiniMax、阶跃(Step)、商汤、讯飞星火、腾讯混元、Google Gemini、Anthropic Claude、Groq、Together、SiliconFlow
  - 本地：Ollama、LM Studio、vLLM
  - 每个预设包含默认 base_url、provider_key、推荐模型列表
- **错误处理**：连接超时、鉴权失败、模型不存在等场景的友好错误返回

#### 2.6.4 crawler_service.py — 爬虫采集服务
- **多源发现**：
  - Bing 搜索：构造搜索 URL，解析结果列表
  - Baidu 搜索：构造搜索 URL，解析结果列表
  - 站内搜索：对 official 类型数据源，拼接站内搜索参数
  - RSS：解析 RSS/Atom feed 获取条目
- **robots.txt 合规**：采集前检查目标站点 robots.txt，遵守 Disallow 规则
- **反反爬策略**：
  - UA 伪装：Chrome 120 User-Agent
  - 限速：同域 2s 间隔，同源 15s 间隔
  - 熔断：连续失败达阈值后暂停 12 小时
- **内容抓取**：httpx 异步请求，支持 HTML 正文提取与 PDF 解析
- **PDF 解析**：下载 PDF 文件，提取文本内容
- **时间过滤**：根据 keyword.date_range_days 过滤过期文章
- **相关性评分**：基于关键词命中频率、位置权重计算 relevance_score
- **去重**：content_hash（对规范化 URL 或内容哈希）判断重复
- **采集流程**：发现(discovery) → 抓取(fetch) → 解析(parse) → 去重(dedup) → 保存(save)，每步记录 CrawlItem 明细
- **后台异步执行**：使用 `asyncio.create_task` 在后台运行，不阻塞 API 响应

#### 2.6.5 local_analysis.py — 本地分析服务
- **jieba 词云（TF-IDF）**：
  - jieba 分词 + 去停用词
  - 计算 TF-IDF 权重
  - 输出词频排序结果（词+权重）
- **图表数据生成**：
  - 来源分布饼图：按 source_name 统计
  - 主题分布饼图：按 keyword.category 统计
  - 频次柱状图：按关键词采集量统计
  - 分布横向柱状图：按来源类型横向展示
  - 趋势折线图：按 publish_date 时间序列统计

#### 2.6.6 scheduler.py — 定时调度器
- 使用 APScheduler AsyncIOScheduler
- 时区：Asia/Shanghai
- 每 30 分钟执行一次：遍历所有 is_active 的 Keyword，判断 `now - last_crawl_at >= crawl_interval`，满足则触发采集
- 在 FastAPI lifespan 中启动与关闭

#### 2.6.7 email_service.py — 邮件服务
- QQ 邮箱 SMTP（smtp.qq.com:465，SSL）
- **验证码邮件**：生成 6 位数字验证码，10 分钟有效，存入缓存（内存字典或数据库）
- **采集通知邮件**：采集完成后根据 notify_on_crawl 发送通知
- 使用 smtplib + ssl，异步发送（run_in_executor）

### 2.7 路由模块（routers/）

所有路由以 `/api` 为前缀。使用 Pydantic schema 做请求/响应校验。

#### 2.7.1 /api/auth — 认证
- `POST /register`：注册（用户名、密码、邮箱、邮箱验证码）
- `POST /login`：登录（用户名+密码），返回 Bearer Token
- `GET /me`：获取当前用户信息（需认证）
- `POST /logout`：登出（删除 AuthSession）

#### 2.7.2 /api/profile — 个人资料
- `GET /`：获取资料
- `PUT /`：更新资料（display_name、email、phone、notify_on_crawl）
- `POST /avatar`：头像上传（multipart，保存到 static 目录）
- `PUT /password`：修改密码（校验旧密码）
- `POST /email-code`：发送邮箱验证码

#### 2.7.3 /api/admin — 管理后台（全部需管理员）
- 角色 CRUD：`GET/POST/PUT/DELETE /roles`
- 用户角色分配：`POST /users/{id}/roles`
- 智能体授权：`POST /providers/{id}/grants`
- Token 用量查看：`GET /token-usage`（支持按用户/时间筛选）

#### 2.7.4 /api/dashboard — 仪表盘
- `GET /stats`：返回统计卡片数据（文章总数、今日新增、关键词数、采集任务数等）+ 最近文章列表

#### 2.7.5 /api/keywords — 关键词
- `GET /`：列表
- `POST /`：创建关键词策略
- `PUT /{id}`：更新
- `DELETE /{id}`：删除
- `GET /{id}/preview`：查询预览（展示该关键词将如何构造搜索查询）

#### 2.7.6 /api/sources — 数据源
- `GET /`：列表
- `POST /`：创建
- `PUT /{id}`：更新
- `DELETE /{id}`：删除

#### 2.7.7 /api/crawler — 爬虫
- `POST /trigger`：触发采集（指定 keyword_id，后台异步执行，立即返回 crawl_log_id）
- `GET /logs`：日志列表（分页）
- `GET /logs/{id}`：日志详情（含统计计数）
- `GET /logs/{id}/items`：日志明细项列表
- `DELETE /logs/{id}`：删除日志

#### 2.7.8 /api/articles — 文章
- `GET /`：列表（分页、按关键词/来源/时间/收藏/已读筛选）
- `GET /{id}`：详情（自动标记 is_read=True）
- `GET /{id}/download`：下载 PDF 文件
- `DELETE /{id}`：删除
- `PUT /{id}/star`：切换收藏状态

#### 2.7.9 /api/providers — AI 智能体
- `GET /presets`：预设列表（17 云端 + 3 本地，含默认配置）
- `GET /`：已配置列表（管理员看全部，普通用户看授权的）
- `POST /`：创建配置（仅管理员）
- `PUT /{id}`：更新（仅管理员）
- `DELETE /{id}`：删除（仅管理员）
- `PUT /{id}/current`：设为当前使用
- `POST /{id}/test`：测试连接
- `GET /{id}/models`：获取可用模型列表

#### 2.7.10 /api/analysis — 分析
- `POST /summary`：AI 摘要（传入 article_id 或文本，调用 ai_service）
- `GET /wordcloud`：词云（本地 jieba，传 keyword_id 或 article_ids）
- `GET /charts`：图表数据（本地统计，多类型）
- `POST /chat`：AI 对话（带上下文，可指定 session_id）
- `GET /history`：历史分析结果列表
- `GET /{id}/download`：下载分析结果（md/docx 格式）
- `GET /usage`：用量统计（按时间/类型汇总 Token）

#### 2.7.11 /api/chat-sessions — 对话会话
- `GET /`：会话列表
- `POST /`：创建会话
- `GET /{id}/messages`：消息列表
- `DELETE /{id}`：删除会话
- `POST /{id}/messages`：发送消息（带记忆 + 自动压缩）
- `POST /{id}/compress`：手动压缩上下文

### 2.8 main.py 启动流程

1. 创建 FastAPI 实例，配置 CORS 中间件
2. lifespan 启动时：
   - 初始化数据库（create_all + 迁移检测）
   - 自动创建 admin 用户
   - 补充默认数据源
   - 启动 APScheduler
3. lifespan 关闭时：关闭调度器
4. 挂载 static 目录（头像、PDF 等静态文件）
5. 注册所有 router

---

## 三、前端架构（Vue 3）

### 3.1 项目初始化

```bash
npm create vite@latest frontend -- --template vue
cd frontend
npm install element-plus echarts three gsap markdown-it highlight.js axios
```

`vite.config.js` 关键配置：
- 开发服务器端口 5173
- API 代理：`/api` → `http://localhost:8000`
- 路径别名 `@` → `src`

### 3.2 全局配置

#### main.js
- 注册 Element Plus（完整引入）
- 注册 Element Plus 图标
- 挂载 Vue 实例

#### 认证状态管理（stores/auth.js 或 api/auth.js）
- `authState`：reactive 对象，包含 `token`、`user`、`isAuthenticated`、`isAdmin`
- token 存储：`localStorage`，key 为 `cezhi-auth-token`
- `isAdmin` 判断：`authState.user?.admin_role === 1`
- 登录成功后写入 token 与 user
- 登出时清除 localStorage 与状态

#### axios 实例（api/http.js）
- baseURL：`/api`
- 请求拦截器：自动添加 `Authorization: Bearer <token>`
- 响应拦截器：
  - 401 状态：清除 token，跳转登录页
  - 统一错误提示（Element Plus ElMessage）

#### 路由（router/index.js）
- 路由守卫：未登录跳转 `/login`
- 路由配置：
  - `/login` → Login.vue
  - `/` → Layout（含侧边栏）→ 子路由：
    - `/home` → Home.vue
    - `/collection` → DataCollection.vue
    - `/articles` → CollectedInfo.vue
    - `/analysis` → DataAnalysis.vue
    - `/ai` → AIAnalysis.vue
    - `/profile` → Profile.vue

### 3.3 布局组件

- **暗色侧边栏布局**：左侧固定暗色导航栏，右侧内容区
- 侧边栏菜单项：首页仪表盘、数据采集、采集信息、数据分析、AI 分析、个人中心
- 顶部：用户头像下拉菜单（个人中心、登出）
- 响应式设计：小屏幕折叠侧边栏

### 3.4 页面详细规范

#### 3.4.1 Login.vue — 登录/注册页
- 登录/注册 Tab 切换（Element Plus Tabs 或自定义）
- 登录表单：用户名、密码
- 注册表单：用户名、密码、邮箱、邮箱验证码（发送验证码按钮+倒计时）
- **Three.js 3D 地球背景**：
  - 星空背景（粒子点）
  - 地球球体（纹理或线框）
  - 城市节点（发光点）
  - 飞线弧（城市间连接弧线，GSAP 动画）
  - 自动旋转
- 表单卡片悬浮于 3D 背景之上，半透明毛玻璃效果

#### 3.4.2 Home.vue — 仪表盘
- 统计卡片行：文章总数、今日新增、关键词数、采集任务数（Element Plus 卡片+图标）
- 3 个 ECharts 图表：
  - 采集趋势折线图（近 7/30 天）
  - 来源分布饼图
  - 关键词频次柱状图
- 最近文章列表（标题、来源、时间、快捷操作）
- 调用 `/api/dashboard/stats`

#### 3.4.3 DataCollection.vue — 数据采集
- 3 个 Tab：
  1. **数据源管理**：表格展示数据源，新增/编辑/删除对话框，source_kind 选择
  2. **关键词策略**：表格展示关键词，新增/编辑对话框（含别名、精确短语、排除词、站点过滤、采集间隔、时间范围），启用/禁用开关
  3. **任务记录**：采集日志表格，状态标签，展开查看明细，**5 秒轮询**刷新 running 状态
- 触发采集按钮（每个关键词行）

#### 3.4.4 CollectedInfo.vue — 采集信息
- 文章列表：
  - 筛选栏：关键词、来源、时间范围、收藏、已读
  - 分页表格
  - 每行：标题、来源、发布时间、收藏星标、已读状态
- **详情抽屉**（Element Plus Drawer）：点击行展开，显示标题、正文、元数据
- PDF 下载按钮
- 收藏切换按钮
- 调用 `/api/articles`

#### 3.4.5 DataAnalysis.vue — 数据分析
- 6 个图表网格布局：
  1. **词云图**：ECharts wordcloud 扩展，展示 TF-IDF 高频词
  2. **来源饼图**：按 source_name 分布
  3. **主题饼图**：按 keyword.category 分布
  4. **频次柱状图**：关键词采集量排名
  5. **分布横向柱状图**：来源类型横向对比
  6. **趋势折线图**：按时间的采集趋势
- 图表支持自适应 resize
- 筛选条件：关键词选择、时间范围

#### 3.4.6 AIAnalysis.vue — AI 分析
- 5 个 Tab：
  1. **AI 配置**（管理员可见完整表单）：
     - 预设智能体列表（17 云端 + 3 本地，卡片展示）
     - 自定义配置表单：名称、provider_key、base_url、api_key、默认模型、上下文窗口
     - 已配置表格：测试连接、设为当前、编辑、删除
     - 测试连接按钮（显示连通状态）
     - 获取模型列表按钮
  2. **摘要分析**：选择文章/输入文本 → 生成 AI 摘要 → Markdown 渲染展示
  3. **智能对话**：
     - 左侧会话列表（新建、切换、删除）
     - 右侧聊天界面（消息气泡，支持 Markdown + 代码高亮）
     - 输入框 + 发送按钮
     - 自动滚动到底部
     - 上下文记忆指示
  4. **权限管理**（仅管理员）：
     - 角色列表 CRUD
     - 用户角色分配
     - 智能体授权给角色
  5. **用量统计**：Token 用量图表（按日/月/类型汇总）
- **权限 UI 差异**：
  - 管理员（admin_role===1）：完整配置表单 + 自定义配置 + 已配置表格 + 权限管理 Tab
  - 普通用户：只读模型信息 + 侧栏查看 + "暂无权限"提示（无法配置）
- **Markdown 渲染**：markdown-it 解析 + highlight.js 代码高亮

#### 3.4.7 Profile.vue — 个人中心
- 头像上传（Element Plus Upload，预览+裁剪）
- 资料表单：display_name、email、phone、notify_on_crawl 开关
- 邮箱验证状态与验证码发送
- 修改密码（旧密码、新密码、确认密码）

### 3.5 公共组件

- **MarkdownRenderer.vue**：封装 markdown-it + highlight.js，接收 content prop，渲染 HTML
- **ChartCard.vue**：图表卡片容器（标题 + ECharts 容器 + loading 状态）
- **EmptyState.vue**：暂无数据/暂无权限提示组件

---

## 四、部署与运行

### 4.1 后端启动

```bash
cd backend
pip install -r requirements.txt
python run.py
# 或 uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- 默认端口 8000
- 首次启动自动建表、创建 admin 用户、补充默认数据源
- SQLite 数据库文件位于 `backend/data/ai_text.db`

### 4.2 前端启动

```bash
cd frontend
npm install
npm run dev
```

- 开发端口 5173
- API 代理至后端 8000

### 4.3 生产构建

```bash
# 前端
cd frontend
npm run build  # 输出至 dist/

# 后端可挂载前端静态文件
# main.py 中 app.mount("/", StaticFiles(directory="../frontend/dist", html=True))
```

### 4.4 环境变量

后端支持通过环境变量覆盖配置（.env 文件）：
- `SMTP_USER`：QQ 邮箱地址
- `SMTP_PASSWORD`：QQ 邮箱授权码
- `SECRET_KEY`：应用密钥
- `ADMIN_PASSWORD`：初始管理员密码（默认 admin）

---

## 五、实现顺序清单

请按以下顺序逐步实现，每一步完成后验证再继续：

### 第一阶段：后端基础
1. 初始化 FastAPI 项目结构与依赖
2. 编写 config.py 配置
3. 编写 database.py 引擎与会话
4. 定义全部 17 个数据模型
5. 实现数据库迁移（SQLITE_COLUMNS + PRAGMA 检测 + ALTER TABLE）
6. 自动创建 admin 用户与默认数据源

### 第二阶段：认证与权限
7. 实现 auth_service.py（PBKDF2 哈希、Token 会话、get_current_user）
8. 实现 /api/auth 路由
9. 实现 permission_service.py（管理员判断、角色权限、Token 限额）
10. 实现 email_service.py（QQ 邮箱验证码）

### 第三阶段：核心业务
11. 实现 /api/keywords 与 /api/sources 路由
12. 实现 crawler_service.py（多源发现、反反爬、PDF 解析、去重、评分）
13. 实现 /api/crawler 路由（触发、日志、明细）
14. 实现 /api/articles 路由（列表、详情、下载、收藏）
15. 实现 /api/dashboard 路由

### 第四阶段：AI 分析
16. 实现 ai_service.py（OpenAI 兼容、17 预设 + 3 本地、摘要、对话 RAG）
17. 实现 local_analysis.py（jieba 词云、图表数据）
18. 实现 /api/analysis 与 /api/chat-sessions 路由
19. 实现 /api/providers 路由（预设、配置、测试、模型）
20. 实现 /api/profile 与 /api/admin 路由

### 第五阶段：调度
21. 实现 scheduler.py（APScheduler 30 分钟检查）
22. 在 main.py lifespan 中集成启动

### 第六阶段：前端基础
23. 初始化 Vue 3 + Vite 项目，安装依赖
24. 配置 axios 拦截器与 authState
25. 配置路由与守卫
26. 实现暗色侧边栏 Layout 布局

### 第七阶段：前端页面
27. Login.vue（含 Three.js 3D 地球）
28. Home.vue（仪表盘 + ECharts）
29. DataCollection.vue（3 Tab + 5 秒轮询）
30. CollectedInfo.vue（列表 + 详情抽屉 + PDF 下载）
31. DataAnalysis.vue（6 图表）
32. AIAnalysis.vue（5 Tab + 权限 UI 差异 + Markdown 渲染）
33. Profile.vue（头像 + 资料 + 改密码）

### 第八阶段：联调与部署
34. 前后端联调，验证所有接口
35. 权限流程验证（管理员 vs 普通用户）
36. 生产构建与静态文件挂载

---

## 六、关键实现要点

1. **全程异步**：后端所有数据库操作与 HTTP 请求均使用 async/await，SQLite 用 aiosqlite 驱动。
2. **Token 安全**：数据库不存明文 token，存 SHA256 哈希；前端 localStorage 存明文 token。
3. **爬虫合规**：必须检查 robots.txt，遵守限速与熔断，避免被封禁。
4. **AI 抽象统一**：所有 AI provider 走 OpenAI 兼容接口，通过 base_url + api_key + model 切换。
5. **权限分层清晰**：管理员 unlimited，普通用户受角色 Token 限额约束，provider 需授权才可见。
6. **记忆压缩**：对话超过 context_window 时，将历史消息摘要压缩为 memory_summary，保留近期消息。
7. **去重机制**：content_hash 基于规范化 URL 或内容摘要，避免重复采集。
8. **前端响应式**：所有 ECharts 图表监听 window resize 自适应；布局支持移动端折叠。

---

请严格按照以上规范实现完整系统。每完成一个阶段请进行验证，确保功能正确后再进入下一阶段。最终交付应包含可独立运行的后端与前端，以及完整的数据库初始化与默认数据。
