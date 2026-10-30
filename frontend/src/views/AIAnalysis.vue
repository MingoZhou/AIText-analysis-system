<template>
  <div class="ai-analysis">
    <el-tabs v-model="activeTab" type="border-card">

      <!-- ========== Tab 1: AI 配置 ========== -->
      <el-tab-pane label="AI 配置" name="config">
        <div class="config-header">
          <el-input
            v-model="providerSearch"
            placeholder="搜索模型平台..."
            :prefix-icon="Search"
            clearable
            style="width: 240px"
          />
          <div class="config-info">
            <span v-if="currentProvider">
              当前模型: <b>{{ currentProvider.default_model || '未设置' }}</b> ({{ currentProvider.name }})
            </span>
            <span v-else class="text-warning">尚未设置当前模型</span>
            <span class="separator">·</span>
            <span>已配置 {{ configuredProviders.length }} 个</span>
          </div>
        </div>

        <!-- 预设供应商网格 -->
        <div class="section-label">预设供应商</div>
        <el-row :gutter="12">
          <el-col :xs="24" :sm="12" :md="8" :lg="6" v-for="item in filteredPresets" :key="item.key" class="provider-col">
            <div
              class="provider-card"
              :data-provider-key="item.key"
              :class="{
                active: item.is_configured,
                current: item.is_current,
                local: item.type === 'local',
                dragging: draggedKey === item.key,
                'drag-over': dragOverKey === item.key,
              }"
              draggable="true"
              @dragstart="handleDragStart($event, item)"
              @dragover.prevent="handleDragOver(item)"
              @drop.prevent="handleDrop(item)"
              @dragend="handleDragEnd"
              @click="openProviderDetail(item)"
            >
              <div class="provider-card-header">
                <span class="provider-name">{{ item.name }}</span>
                <div class="provider-card-tools">
                  <span v-if="item.is_current" class="status-dot current"></span>
                  <span v-else-if="item.is_configured" class="status-dot configured"></span>
                  <el-tooltip content="拖动排序" placement="top">
                    <el-icon class="drag-handle" @click.stop @pointerdown.stop.prevent="handlePointerDown($event, item)"><Rank /></el-icon>
                  </el-tooltip>
                </div>
              </div>
              <div class="provider-desc">{{ item.description }}</div>
              <div class="provider-type">{{ item.type === 'local' ? '本地部署' : '预设' }}</div>
            </div>
          </el-col>

          <!-- 自定义配置 -->
          <el-col v-if="isAdmin" :xs="24" :sm="12" :md="8" :lg="6" class="provider-col">
            <div class="provider-card custom" @click="openCustomDialog">
              <div class="provider-card-header">
                <span class="provider-name">+ 自定义配置</span>
              </div>
              <div class="provider-desc">添加自定义 API 提供商</div>
              <div class="provider-type">自定义</div>
            </div>
          </el-col>
        </el-row>

        <!-- 已配置列表（仅管理员可见） -->
        <template v-if="isAdmin">
        <div class="section-label" style="margin-top: 20px">已配置提供商</div>
        <el-table :data="configuredProviders" stripe style="width: 100%" v-loading="loadingProviders">
          <el-table-column prop="name" label="名称" width="180" />
          <el-table-column prop="provider_key" label="类型" width="120">
            <template #default="{ row }">
              <el-tag :type="row.provider_type === 'local' ? 'warning' : 'success'" size="small">
                {{ row.provider_type === 'local' ? '本地' : row.provider_type === 'preset' ? '预设' : '自定义' }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="base_url" label="Base URL" min-width="250" show-overflow-tooltip />
          <el-table-column prop="default_model" label="模型" width="200" show-overflow-tooltip>
            <template #default="{ row }">{{ row.default_model || '未设置' }}</template>
          </el-table-column>
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag v-if="row.is_current" type="primary" size="small">当前</el-tag>
              <el-tag v-else type="info" size="small">备用</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="230" fixed="right">
            <template #default="{ row }">
              <div class="action-row">
                <el-button size="small" link @click="openEditProvider(row)">编辑</el-button>
                <el-button v-if="!row.is_current" size="small" link type="primary" @click="setCurrentProvider(row)">设为当前</el-button>
                <el-button size="small" link type="danger" @click="deleteProvider(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
        </template>
      </el-tab-pane>

      <!-- ========== Tab 2: 摘要分析 ========== -->
      <el-tab-pane label="摘要分析" name="analysis">
        <div class="analysis-control">
          <el-card shadow="never">
            <el-form :inline="true">
              <el-form-item label="选择关键词">
                <el-select v-model="analysisKeywordId" placeholder="按关键词分析" clearable filterable style="width: 200px" @change="onKeywordChange">
                  <el-option v-for="kw in keywords" :key="kw.id" :label="kw.keyword" :value="kw.id" />
                </el-select>
              </el-form-item>
              <el-form-item label="或选择文章">
                <el-select v-model="analysisArticleIds" multiple placeholder="可多选文章" filterable style="width: 300px" :disabled="!!analysisKeywordId" :loading="analysisArticlesLoading">
                  <el-option v-for="art in analysisArticles" :key="art.id" :label="art.title" :value="art.id" />
                </el-select>
              </el-form-item>
              <el-form-item>
                <el-button type="primary" :loading="analysisLoading" @click="runSummary">
                  <el-icon><Document /></el-icon> 生成摘要
                </el-button>
              </el-form-item>
            </el-form>
          </el-card>
        </div>

        <!-- 摘要结果 -->
        <el-card v-if="summaryResult" class="result-card" shadow="never">
          <template #header>
            <div class="result-header">
              <span>摘要分析结果</span>
              <div class="result-header-right">
                <el-tag size="small">{{ summaryResult.provider }} · {{ summaryResult.model }}</el-tag>
                <el-button size="small" type="success" plain @click="downloadSummary('md')">
                  <el-icon><Download /></el-icon> .md
                </el-button>
                <el-button size="small" type="primary" plain @click="downloadSummary('docx')">
                  <el-icon><Document /></el-icon> Word
                </el-button>
                <el-button size="small" text type="info" @click="closeSummaryResult">
                  <el-icon><Close /></el-icon> 收起
                </el-button>
              </div>
            </div>
          </template>
          <div class="summary-content markdown-body" v-html="formatSummary(summaryResult.summary)"></div>
        </el-card>

        <!-- 历史摘要列表 -->
        <div class="section-label" style="margin-top: 20px">历史摘要</div>
        <el-table :data="summaryHistory" stripe style="width: 100%" v-loading="loadingHistory">
          <el-table-column prop="created_at" label="时间" width="180">
            <template #default="{ row }">{{ formatTime(row.created_at) }}</template>
          </el-table-column>
          <el-table-column prop="model" label="模型" width="150" />
          <el-table-column label="摘要预览" min-width="300">
            <template #default="{ row }">{{ (row.result?.summary || '').substring(0, 80) }}...</template>
          </el-table-column>
          <el-table-column label="操作" width="220" fixed="right">
            <template #default="{ row }">
              <div class="action-row">
                <el-button size="small" link type="primary" @click="viewHistorySummary(row)">查看</el-button>
                <el-button size="small" link type="success" @click="downloadHistorySummary(row, 'md')">.md</el-button>
                <el-button size="small" link type="primary" @click="downloadHistorySummary(row, 'docx')">Word</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>

        <el-empty v-if="!summaryResult && summaryHistory.length === 0" description="选择关键词或文章后点击生成摘要按钮" />
      </el-tab-pane>

      <!-- ========== Tab 3: 智能对话 ========== -->
      <el-tab-pane label="智能对话" name="chat">
        <div class="chat-layout">
          <!-- 左侧：会话列表 -->
          <div class="chat-sidebar">
            <div class="chat-sidebar-header">
              <el-button type="primary" size="small" style="width: 100%" @click="createSession">
                <el-icon><Plus /></el-icon> 新建对话
              </el-button>
            </div>
            <div class="session-list">
              <div
                v-for="s in sessions"
                :key="s.id"
                class="session-item"
                :class="{ active: currentSessionId === s.id }"
                @click="selectSession(s.id)"
              >
                <div class="session-info">
                  <div class="session-title">{{ s.title }}</div>
                  <div class="session-meta">
                    <span>{{ s.message_count }} 条消息</span>
                    <span v-if="s.context_compressed" class="memory-badge">已压缩</span>
                  </div>
                </div>
                <div class="session-actions" @click.stop>
                  <el-dropdown trigger="click" @command="(cmd) => handleSessionCommand(cmd, s)">
                    <el-icon class="session-more"><MoreFilled /></el-icon>
                    <template #dropdown>
                      <el-dropdown-menu>
                        <el-dropdown-item command="rename">重命名</el-dropdown-item>
                        <el-dropdown-item command="delete" divided>删除</el-dropdown-item>
                      </el-dropdown-menu>
                    </template>
                  </el-dropdown>
                </div>
              </div>
              <el-empty v-if="sessions.length === 0" description="暂无对话" :image-size="60" />
            </div>
          </div>

          <!-- 右侧：对话区域 -->
          <div class="chat-main">
            <!-- 对话头部 -->
            <div class="chat-header" v-if="currentSession">
              <div class="chat-header-info">
                <span class="chat-title">{{ currentSession.title }}</span>
                <div class="chat-model-bar">
                  <el-tag size="small" type="info">{{ currentSession.model || '默认模型' }}</el-tag>
                  <el-select
                    v-model="currentSession.model"
                    size="small"
                    placeholder="切换模型"
                    filterable
                    allow-create
                    style="width: 180px"
                    @change="switchModel"
                  >
                    <el-option v-for="m in availableModels" :key="m" :label="m" :value="m" />
                  </el-select>
                  <el-select
                    v-model="currentSession.keyword_id"
                    size="small"
                    placeholder="上下文关键词"
                    clearable
                    filterable
                    style="width: 160px"
                    @change="updateSessionKeyword"
                  >
                    <el-option v-for="kw in keywords" :key="kw.id" :label="kw.keyword" :value="kw.id" />
                  </el-select>
                  <el-tooltip v-if="currentSession.memory_summary" :content="currentSession.memory_summary.substring(0, 200) + '...'" placement="bottom">
                    <el-tag size="small" type="success">记忆已启用</el-tag>
                  </el-tooltip>
                  <el-tooltip content="手动压缩上下文" placement="bottom">
                    <el-button size="small" text @click="compressContext" :loading="compressing">
                      <el-icon><MagicStick /></el-icon>
                    </el-button>
                  </el-tooltip>
                </div>
              </div>
            </div>

            <!-- 消息区域 -->
            <div class="chat-messages" ref="chatMessagesRef">
              <div v-for="(msg, i) in currentMessages" :key="i" :class="['chat-msg', msg.role]">
                <div class="chat-avatar" v-if="msg.role === 'assistant'">AI</div>
                <div class="chat-bubble">
                  <div v-if="msg.role === 'assistant'" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
                  <div v-else>{{ msg.content }}</div>
                  <div v-if="msg.role === 'assistant' && msg.elapsed_ms" class="chat-meta">
                    {{ formatChatMeta(msg) }}
                  </div>
                </div>
                <div class="chat-avatar user-avatar" v-if="msg.role === 'user'">我</div>
              </div>
              <div v-if="chatLoading" class="chat-msg assistant">
                <div class="chat-avatar">AI</div>
                <div class="chat-bubble loading">正在等待 {{ currentProvider?.name || 'AI' }} 返回...</div>
              </div>
              <el-empty v-if="!currentSession && sessions.length === 0" description="点击「新建对话」开始聊天" />
            </div>

            <!-- 输入区域 -->
            <div class="chat-input" v-if="currentSession">
              <el-input
                v-model="chatInput"
                placeholder="输入问题，基于采集的文章内容进行问答..."
                @keyup.enter="sendChat"
                :disabled="chatLoading"
              >
                <template #append>
                  <el-button :loading="chatLoading" @click="sendChat">发送</el-button>
                </template>
              </el-input>
            </div>
          </div>
        </div>
      </el-tab-pane>

      <!-- ========== Tab 5: 权限管理（仅管理员可见） ========== -->
      <el-tab-pane v-if="isAdmin" label="权限管理" name="permission">
        <div v-loading="permLoading" class="permission-page">
          <!-- 角色管理 -->
          <div class="section-label">角色管理</div>
          <div class="perm-toolbar">
            <el-button type="primary" size="small" @click="openRoleDialog(null)">
              <el-icon><Plus /></el-icon> 新建角色
            </el-button>
          </div>
          <el-table :data="roles" stripe style="width: 100%" class="perm-table">
            <el-table-column prop="name" label="角色名称" width="140" />
            <el-table-column prop="description" label="描述" min-width="180" show-overflow-tooltip />
            <el-table-column label="日 Token 限额" width="130">
              <template #default="{ row }">
                <span v-if="row.daily_token_limit > 0">{{ row.daily_token_limit.toLocaleString() }}</span>
                <el-tag v-else type="danger" size="small">禁止使用</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="月 Token 限额" width="140">
              <template #default="{ row }">{{ row.monthly_token_limit > 0 ? row.monthly_token_limit.toLocaleString() : '—' }}</template>
            </el-table-column>
            <el-table-column prop="user_count" label="用户数" width="80" />
            <el-table-column prop="provider_count" label="授权智能体" width="100" />
            <el-table-column label="操作" width="160" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link @click="openRoleDialog(row)">编辑</el-button>
                <el-button size="small" link @click="openGrantDialog(row)">授权</el-button>
                <el-button size="small" link type="danger" @click="deleteRole(row)">删除</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- 用户角色分配 -->
          <div class="section-label" style="margin-top: 20px">用户角色分配</div>
          <el-table :data="userList" stripe style="width: 100%" class="perm-table">
            <el-table-column prop="username" label="用户名" width="140" />
            <el-table-column prop="display_name" label="显示名" width="140" />
            <el-table-column prop="email" label="邮箱" min-width="200" show-overflow-tooltip />
            <el-table-column label="身份" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.admin_role === 1" type="danger" size="small">管理员</el-tag>
                <el-tag v-else type="info" size="small">普通用户</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="已分配角色" min-width="200">
              <template #default="{ row }">
                <el-tag v-for="r in row.roles" :key="r.id" size="small" class="role-tag" closable @close="removeUserRole(row, r)">
                  {{ r.name }}
                </el-tag>
                <span v-if="!row.roles || row.roles.length === 0" class="text-muted">未分配</span>
              </template>
            </el-table-column>
            <el-table-column label="操作" width="120" fixed="right">
              <template #default="{ row }">
                <el-button size="small" link type="primary" @click="openAssignDialog(row)" :disabled="row.admin_role === 1">分配角色</el-button>
              </template>
            </el-table-column>
          </el-table>

          <!-- Token 用量总览 -->
          <div class="section-label" style="margin-top: 20px">Token 用量总览</div>
          <el-table :data="tokenUsageList" stripe style="width: 100%" class="perm-table">
            <el-table-column prop="username" label="用户" width="140" />
            <el-table-column label="身份" width="100">
              <template #default="{ row }">
                <el-tag v-if="row.is_admin" type="danger" size="small">管理员</el-tag>
                <el-tag v-else size="small">普通</el-tag>
              </template>
            </el-table-column>
            <el-table-column label="今日用量" width="140">
              <template #default="{ row }">
                <span v-if="row.is_admin" class="text-muted">不限额</span>
                <span v-else>{{ row.daily_used.toLocaleString() }} / {{ row.daily_limit > 0 ? row.daily_limit.toLocaleString() : '禁止' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="本月用量" width="140">
              <template #default="{ row }">
                <span v-if="row.is_admin" class="text-muted">不限额</span>
                <span v-else>{{ row.monthly_used.toLocaleString() }} / {{ row.monthly_limit > 0 ? row.monthly_limit.toLocaleString() : '禁止' }}</span>
              </template>
            </el-table-column>
            <el-table-column label="进度" min-width="200">
              <template #default="{ row }">
                <el-progress v-if="!row.is_admin && row.daily_limit > 0"
                  :percentage="Math.min(Math.round(row.daily_used / row.daily_limit * 100), 100)"
                  :color="row.daily_used / row.daily_limit > 0.8 ? '#f56c6c' : '#409eff'"
                  :stroke-width="14"
                />
                <span v-else-if="row.is_admin" class="text-muted">—</span>
                <el-tag v-else type="danger" size="small">未设置限额</el-tag>
              </template>
            </el-table-column>
          </el-table>
        </div>
      </el-tab-pane>

      <!-- ========== Tab 4: 用量统计 ========== -->
      <el-tab-pane label="用量统计" name="usage">
        <div v-loading="usageLoading" class="usage-page">
          <!-- 概览卡片 -->
          <el-row :gutter="12" class="usage-overview">
            <el-col :xs="12" :sm="6">
              <div class="stat-card stat-blue">
                <div class="stat-icon"><el-icon><Document /></el-icon></div>
                <div class="stat-body">
                  <div class="stat-value">{{ usageData.total_analysis }}</div>
                  <div class="stat-label">AI 分析次数</div>
                </div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card stat-green">
                <div class="stat-icon"><el-icon><ChatDotRound /></el-icon></div>
                <div class="stat-body">
                  <div class="stat-value">{{ usageData.total_chat_messages }}</div>
                  <div class="stat-label">对话消息数</div>
                </div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card stat-orange">
                <div class="stat-icon"><el-icon><Connection /></el-icon></div>
                <div class="stat-body">
                  <div class="stat-value">{{ usageData.total_sessions }}</div>
                  <div class="stat-label">对话会话数</div>
                </div>
              </div>
            </el-col>
            <el-col :xs="12" :sm="6">
              <div class="stat-card stat-purple">
                <div class="stat-icon"><el-icon><Coin /></el-icon></div>
                <div class="stat-body">
                  <div class="stat-value">{{ formatTokens(usageData.total_tokens) }}</div>
                  <div class="stat-label">估算 Token 用量</div>
                </div>
              </div>
            </el-col>
          </el-row>

          <!-- 分类统计 -->
          <el-row :gutter="12" style="margin-top: 16px">
            <el-col :xs="24" :sm="12" :md="8">
              <el-card shadow="never" class="usage-card">
                <template #header><span class="card-title">按分析类型</span></template>
                <div class="type-list">
                  <div class="type-item" v-for="item in typeBreakdown" :key="item.key">
                    <span class="type-dot" :style="{ background: item.color }"></span>
                    <span class="type-name">{{ item.label }}</span>
                    <span class="type-count">{{ item.count }}</span>
                  </div>
                </div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="16">
              <el-card shadow="never" class="usage-card">
                <template #header><span class="card-title">近 7 天趋势</span></template>
                <div ref="dailyChartRef" class="chart-container"></div>
              </el-card>
            </el-col>
          </el-row>

          <!-- 模型 & 提供商分布 -->
          <el-row :gutter="12" style="margin-top: 12px">
            <el-col :xs="24" :sm="12" :md="12">
              <el-card shadow="never" class="usage-card">
                <template #header><span class="card-title">模型使用分布</span></template>
                <div v-if="usageData.by_model.length === 0" class="empty-tip">暂无数据</div>
                <div v-else ref="modelChartRef" class="chart-container"></div>
              </el-card>
            </el-col>
            <el-col :xs="24" :sm="12" :md="12">
              <el-card shadow="never" class="usage-card">
                <template #header><span class="card-title">提供商使用分布</span></template>
                <div v-if="usageData.by_provider.length === 0" class="empty-tip">暂无数据</div>
                <div v-else class="provider-list">
                  <div class="provider-bar-item" v-for="(item, i) in usageData.by_provider" :key="item.provider_id">
                    <div class="provider-bar-header">
                      <span class="provider-bar-name">{{ item.name }}</span>
                      <span class="provider-bar-count">{{ item.count }} 次</span>
                    </div>
                    <div class="provider-bar-track">
                      <div class="provider-bar-fill" :style="{ width: providerBarWidth(item.count) + '%', background: barColors[i % barColors.length] }"></div>
                    </div>
                  </div>
                </div>
              </el-card>
            </el-col>
          </el-row>
        </div>
      </el-tab-pane>

    </el-tabs>

    <!-- ========== 提供商详情抽屉 ========== -->
    <el-drawer v-model="providerDrawer" :title="editingProvider?.name || '配置提供商'" size="480px" direction="rtl">
      <div class="provider-detail">
        <div class="detail-desc">{{ editingProvider?.description }}</div>

        <!-- 管理员：完整配置表单 -->
        <template v-if="isAdmin">
          <el-form label-position="top" class="detail-form">
            <el-form-item label="Base URL">
              <el-input v-model="formData.base_url" placeholder="https://api.example.com/v1" />
              <div class="form-hint">请求将发送到 {{ formData.base_url }}/chat/completions</div>
            </el-form-item>
            <el-form-item label="API Key">
              <el-input v-model="formData.api_key" type="password" show-password placeholder="输入 API Key（本地服务可留空）" />
              <div class="form-hint">部分模型服务商需要先填写有效的 API Key，才能获取模型列表。</div>
            </el-form-item>
            <el-form-item label="默认模型">
              <div class="model-row">
                <el-select v-model="formData.default_model" filterable allow-create placeholder="选择或输入模型名称" style="flex: 1">
                  <el-option v-for="m in modelList" :key="m" :label="m" :value="m" />
                </el-select>
                <el-button :loading="refreshingModels" @click="refreshModels">刷新模型列表</el-button>
              </div>
            </el-form-item>
            <el-form-item label="上下文窗口">
              <el-input-number v-model="formData.context_window" :min="0" :step="1000" style="width: 100%" />
              <div class="form-hint">留 0 或空表示自动检测。可手动指定 token 数。</div>
            </el-form-item>
          </el-form>
          <div class="detail-actions">
            <el-button @click="testConnection" :loading="testing">测试连接</el-button>
            <el-button type="primary" @click="saveProvider">保存配置</el-button>
            <el-button v-if="formData.id && !formData.is_current" type="success" @click="setCurrentAndSave">设为当前模型</el-button>
          </div>
        </template>

        <!-- 普通用户：只读模型信息 -->
        <template v-else>
          <div v-if="!formData.id" class="no-permission-tip">
            <el-result icon="info" title="暂无权限" sub-title="您尚未被授权使用此智能体，请联系管理员开通权限。" />
          </div>
          <div v-else>
            <el-descriptions :column="1" border class="readonly-detail">
              <el-descriptions-item label="模型名称">{{ formData.default_model || '未设置' }}</el-descriptions-item>
              <el-descriptions-item label="提供商">{{ editingProvider?.name }}</el-descriptions-item>
              <el-descriptions-item label="类型">
                <el-tag size="small" :type="formData.provider_type === 'local' ? 'warning' : 'success'">
                  {{ formData.provider_type === 'local' ? '本地部署' : formData.provider_type === 'preset' ? '预设' : '自定义' }}
                </el-tag>
              </el-descriptions-item>
              <el-descriptions-item label="状态">
                <el-tag v-if="formData.is_current" type="primary" size="small">当前使用</el-tag>
                <el-tag v-else type="info" size="small">备用</el-tag>
              </el-descriptions-item>
            </el-descriptions>
            <div class="detail-actions">
              <el-button v-if="!formData.is_current" type="success" @click="setCurrentForUser">设为当前模型</el-button>
            </div>
          </div>
        </template>
      </div>
    </el-drawer>

    <!-- ========== 自定义配置弹窗 ========== -->
    <el-dialog v-model="customDialog" title="添加自定义配置" width="500px">
      <el-form label-position="top">
        <el-form-item label="名称">
          <el-input v-model="customForm.name" placeholder="例如: 我的 API" />
        </el-form-item>
        <el-form-item label="Base URL">
          <el-input v-model="customForm.base_url" placeholder="https://api.example.com/v1" />
        </el-form-item>
        <el-form-item label="API Key">
          <el-input v-model="customForm.api_key" type="password" show-password />
        </el-form-item>
        <el-form-item label="默认模型">
          <el-input v-model="customForm.default_model" placeholder="模型名称" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="customDialog = false">取消</el-button>
        <el-button type="primary" @click="saveCustomProvider">添加并选中</el-button>
      </template>
    </el-dialog>

    <!-- ========== 角色编辑弹窗 ========== -->
    <el-dialog v-model="roleDialog" :title="roleForm.id ? '编辑角色' : '新建角色'" width="480px">
      <el-form label-position="top">
        <el-form-item label="角色名称">
          <el-input v-model="roleForm.name" placeholder="例如: 普通用户、VIP、试用" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="roleForm.description" type="textarea" :rows="2" placeholder="角色描述" />
        </el-form-item>
        <el-form-item label="日 Token 限额">
          <el-input-number v-model="roleForm.daily_token_limit" :min="0" :step="10000" style="width: 100%" />
          <div class="form-hint">设为 0 表示禁止使用 AI 功能</div>
        </el-form-item>
        <el-form-item label="月 Token 限额">
          <el-input-number v-model="roleForm.monthly_token_limit" :min="0" :step="100000" style="width: 100%" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="roleDialog = false">取消</el-button>
        <el-button type="primary" @click="saveRole">保存</el-button>
      </template>
    </el-dialog>

    <!-- ========== 智能体授权弹窗 ========== -->
    <el-dialog v-model="grantDialog" :title="`授权智能体 — ${currentGrantRole?.name || ''}`" width="600px">
      <el-table :data="grantProviderList" stripe style="width: 100%" max-height="400">
        <el-table-column prop="name" label="智能体" width="160" />
        <el-table-column prop="default_model" label="模型" min-width="180" show-overflow-tooltip />
        <el-table-column label="已授权" width="100">
          <template #default="{ row }">
            <el-tag v-if="row.granted" type="success" size="small">已授权</el-tag>
            <el-tag v-else type="info" size="small">未授权</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="100">
          <template #default="{ row }">
            <el-button v-if="!row.granted" size="small" link type="primary" @click="addGrant(row)">授权</el-button>
            <el-button v-else size="small" link type="danger" @click="removeGrant(row)">撤销</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>

    <!-- ========== 用户角色分配弹窗 ========== -->
    <el-dialog v-model="assignDialog" :title="`分配角色 — ${currentAssignUser?.username || ''}`" width="460px">
      <el-select v-model="selectedRoleIds" multiple placeholder="选择角色" style="width: 100%">
        <el-option v-for="r in roles" :key="r.id" :label="`${r.name}（日限 ${r.daily_token_limit.toLocaleString()}）`" :value="r.id" />
      </el-select>
      <div class="form-hint" style="margin-top: 8px">一个用户可分配多个角色，Token 限额取最大值</div>
      <template #footer>
        <el-button @click="assignDialog = false">取消</el-button>
        <el-button type="primary" @click="saveUserRoles">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Search, Document, Rank, Plus, MoreFilled, Download, MagicStick, Close, DataAnalysis, ChatDotRound, Connection, Coin } from '@element-plus/icons-vue'
import { providerApi, analysisApi, keywordApi, articleApi, chatSessionApi, adminApi } from '../api'
import { authState } from '../auth'
import MarkdownIt from 'markdown-it'
import hljs from 'highlight.js'
import * as echarts from 'echarts'

// ---- Markdown 渲染器 ----
const md = new MarkdownIt({
  html: false,
  linkify: true,
  breaks: true,
  highlight(str, lang) {
    if (lang && hljs.getLanguage(lang)) {
      try {
        return `<pre class="md-code-block"><code>${hljs.highlight(str, { language: lang }).value}</code></pre>`
      } catch (_) { /* fallback */ }
    }
    return `<pre class="md-code-block"><code>${md.utils.escapeHtml(str)}</code></pre>`
  },
})

function renderMarkdown(text) {
  if (!text) return ''
  return md.render(text)
}

const activeTab = ref('config')

// 管理员判断
const isAdmin = computed(() => authState.user?.admin_role === 1)

// ========== AI 配置 ==========
const providerSearch = ref('')
const loadingProviders = ref(false)
const presetList = ref([])
const localPresets = ref([])
const providerOrder = ref([])
const configuredProviders = ref([])
const providerDrawer = ref(false)
const editingProvider = ref(null)
const modelList = ref([])
const refreshingModels = ref(false)
const testing = ref(false)
const draggedKey = ref('')
const dragOverKey = ref('')
let suppressCardOpen = false
let pointerTargetKey = ''

const formData = reactive({
  id: null,
  name: '',
  provider_key: 'custom',
  provider_type: 'custom',
  base_url: '',
  api_key: '',
  default_model: '',
  context_window: 0,
  is_current: false,
})

const customDialog = ref(false)
const customForm = reactive({ name: '', base_url: '', api_key: '', default_model: '' })

const currentProvider = computed(() => configuredProviders.value.find(p => p.is_current))

const availableModels = computed(() => {
  if (!currentProvider.value) return []
  return modelList.value.length > 0 ? modelList.value : (currentProvider.value.default_model ? [currentProvider.value.default_model] : [])
})

const orderedPresets = computed(() => {
  const cards = [...presetList.value, ...localPresets.value]
  const positions = new Map(providerOrder.value.map((key, index) => [key, index]))
  return cards.sort((a, b) => (positions.get(a.key) ?? 9999) - (positions.get(b.key) ?? 9999))
})

const filteredPresets = computed(() => {
  if (!providerSearch.value) return orderedPresets.value
  const query = providerSearch.value.toLowerCase()
  return orderedPresets.value.filter(p => p.name.toLowerCase().includes(query))
})

async function loadPresets() {
  const [presetRes, localRes, configRes, orderRes] = await Promise.all([
    providerApi.listPresets(),
    providerApi.listLocalPresets(),
    providerApi.list(),
    providerApi.getPresetOrder(),
  ])
  presetList.value = presetRes.data.map(p => ({ ...p, is_configured: false, is_current: false }))
  localPresets.value = localRes.data.map(p => ({ ...p, is_configured: false, is_current: false }))
  configuredProviders.value = configRes.data
  providerOrder.value = orderRes.data.keys || []

  for (const cp of configuredProviders.value) {
    const match = presetList.value.find(p => p.key === cp.provider_key)
    if (match) {
      match.is_configured = true
      match.is_current = cp.is_current
      match.config_id = cp.id
    }
    const localMatch = localPresets.value.find(p => p.key === cp.provider_key)
    if (localMatch) {
      localMatch.is_configured = true
      localMatch.is_current = cp.is_current
      localMatch.config_id = cp.id
    }
  }
}

function openProviderDetail(item) {
  if (suppressCardOpen) return
  editingProvider.value = item
  const existing = configuredProviders.value.find(p => p.provider_key === item.key)
  if (existing) {
    Object.assign(formData, {
      id: existing.id,
      name: existing.name,
      provider_key: existing.provider_key,
      provider_type: existing.provider_type,
      base_url: existing.base_url,
      api_key: existing.api_key,
      default_model: existing.default_model,
      context_window: existing.context_window,
      is_current: existing.is_current,
    })
  } else {
    Object.assign(formData, {
      id: null,
      name: item.name,
      provider_key: item.key,
      provider_type: item.type,
      base_url: item.base_url,
      api_key: '',
      default_model: item.default_model || '',
      context_window: item.context_window || 0,
      is_current: false,
    })
  }
  modelList.value = []
  providerDrawer.value = true
}

function handleDragStart(event, item) {
  draggedKey.value = item.key
  dragOverKey.value = ''
  event.dataTransfer.effectAllowed = 'move'
  event.dataTransfer.setData('text/plain', item.key)
}

function handleDragOver(item) {
  if (draggedKey.value && draggedKey.value !== item.key) dragOverKey.value = item.key
}

async function handleDrop(item) {
  const sourceKey = draggedKey.value
  handleDragEnd()
  await moveProvider(sourceKey, item.key)
}

async function moveProvider(sourceKey, targetKey) {
  if (!sourceKey || !targetKey || sourceKey === targetKey) return
  const keys = orderedPresets.value.map(provider => provider.key)
  const sourceIndex = keys.indexOf(sourceKey)
  const targetIndex = keys.indexOf(targetKey)
  if (sourceIndex < 0 || targetIndex < 0) return
  keys.splice(sourceIndex, 1)
  keys.splice(targetIndex, 0, sourceKey)
  providerOrder.value = keys
  suppressCardOpen = true
  try {
    const response = await providerApi.updatePresetOrder(keys)
    providerOrder.value = response.data.keys
    ElMessage.success('供应商顺序已保存')
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '保存排序失败'))
    await loadPresets()
  } finally {
    setTimeout(() => { suppressCardOpen = false }, 0)
  }
}

function handleDragEnd() {
  draggedKey.value = ''
  dragOverKey.value = ''
}

function handlePointerDown(event, item) {
  draggedKey.value = item.key
  pointerTargetKey = item.key
  event.currentTarget.setPointerCapture?.(event.pointerId)
  window.addEventListener('pointermove', handlePointerMove)
  window.addEventListener('pointerup', handlePointerUp, { once: true })
  window.addEventListener('pointercancel', handlePointerCancel, { once: true })
}

function handlePointerMove(event) {
  const card = document.elementFromPoint(event.clientX, event.clientY)?.closest('[data-provider-key]')
  const key = card?.dataset.providerKey || ''
  if (key && key !== draggedKey.value) {
    pointerTargetKey = key
    dragOverKey.value = key
  }
}

async function handlePointerUp() {
  const sourceKey = draggedKey.value
  const targetKey = pointerTargetKey
  cleanupPointerDrag()
  await moveProvider(sourceKey, targetKey)
}

function handlePointerCancel() {
  cleanupPointerDrag()
}

function cleanupPointerDrag() {
  window.removeEventListener('pointermove', handlePointerMove)
  window.removeEventListener('pointerup', handlePointerUp)
  window.removeEventListener('pointercancel', handlePointerCancel)
  pointerTargetKey = ''
  handleDragEnd()
}

function apiErrorMessage(error, fallback) {
  const detail = error.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail?.message) return detail.message
  return fallback
}

function openEditProvider(row) {
  editingProvider.value = { name: row.name, description: '', key: row.provider_key, type: row.provider_type }
  Object.assign(formData, { ...row })
  providerDrawer.value = true
}

async function refreshModels() {
  if (!formData.base_url) {
    ElMessage.warning('请先填写 Base URL')
    return
  }
  refreshingModels.value = true
  try {
    const res = await providerApi.getModels({ base_url: formData.base_url, api_key: formData.api_key })
    modelList.value = res.data.models || []
    if (modelList.value.length === 0) {
      ElMessage.warning('未获取到模型列表，请检查 API Key')
    } else {
      ElMessage.success(`获取到 ${modelList.value.length} 个模型`)
    }
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '获取模型列表失败'))
  } finally {
    refreshingModels.value = false
  }
}

async function testConnection() {
  if (!formData.base_url) {
    ElMessage.warning('请先填写 Base URL')
    return
  }
  testing.value = true
  try {
    const res = await providerApi.testConnection({ base_url: formData.base_url, api_key: formData.api_key })
    if (res.data.success) {
      ElMessage.success(res.data.message)
    } else {
      ElMessage.error(res.data.message)
    }
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '测试连接失败'))
  } finally {
    testing.value = false
  }
}

async function saveProvider() {
  const payload = {
    name: formData.name,
    provider_key: formData.provider_key,
    provider_type: formData.provider_type,
    base_url: formData.base_url,
    api_key: formData.api_key,
    default_model: formData.default_model,
    context_window: formData.context_window,
  }
  try {
    if (formData.id) {
      await providerApi.update(formData.id, payload)
      ElMessage.success('配置已更新')
    } else {
      const res = await providerApi.create(payload)
      formData.id = res.data.id
      ElMessage.success('配置已保存')
    }
    providerDrawer.value = false
    await loadPresets()
  } catch {
    ElMessage.error('保存失败')
  }
}

async function setCurrentProvider(row) {
  try {
    await providerApi.setCurrent(row.id)
    ElMessage.success(`已设为当前: ${row.name}`)
    await loadPresets()
  } catch {
    ElMessage.error('设置失败')
  }
}

async function setCurrentAndSave() {
  await saveProvider()
  if (formData.id) {
    await providerApi.setCurrent(formData.id)
    ElMessage.success('已设为当前模型')
    await loadPresets()
  }
}

async function deleteProvider(row) {
  await ElMessageBox.confirm(`确认删除 ${row.name}？`, '提示', { type: 'warning' })
  await providerApi.delete(row.id)
  ElMessage.success('已删除')
  await loadPresets()
}

function openCustomDialog() {
  Object.assign(customForm, { name: '', base_url: '', api_key: '', default_model: '' })
  customDialog.value = true
}

async function saveCustomProvider() {
  if (!customForm.name || !customForm.base_url) {
    ElMessage.warning('请填写名称和 Base URL')
    return
  }
  try {
    const res = await providerApi.create({
      name: customForm.name,
      provider_key: 'custom',
      provider_type: 'custom',
      base_url: customForm.base_url,
      api_key: customForm.api_key,
      default_model: customForm.default_model,
      context_window: 0,
    })
    await providerApi.setCurrent(res.data.id)
    ElMessage.success('已添加并设为当前')
    customDialog.value = false
    await loadPresets()
  } catch {
    ElMessage.error('添加失败')
  }
}

// ========== 摘要分析 ==========
const keywords = ref([])
const analysisArticles = ref([])
const analysisArticlesLoading = ref(false)
const analysisKeywordId = ref(null)
const analysisArticleIds = ref([])
const analysisLoading = ref(false)
const summaryResult = ref(null)
const summaryHistory = ref([])
const loadingHistory = ref(false)
let lastSummaryResultId = null

async function loadKeywords() {
  const res = await keywordApi.list()
  keywords.value = res.data
}

async function onKeywordChange() {
  analysisArticleIds.value = []
  await loadAnalysisArticles(analysisKeywordId.value || null)
}

async function loadAnalysisArticles(keywordId = null) {
  analysisArticlesLoading.value = true
  try {
    const params = { page: 1, page_size: 100 }
    if (keywordId) params.keyword_id = keywordId
    const res = await articleApi.list(params)
    analysisArticles.value = res.data.items || []
  } catch {
    analysisArticles.value = []
    ElMessage.error('加载文章列表失败')
  } finally {
    analysisArticlesLoading.value = false
  }
}

async function runSummary() {
  const hasSelection = analysisKeywordId.value || analysisArticleIds.value.length > 0
  if (!hasSelection) {
    ElMessage.warning('请先选择关键词或文章')
    return
  }
  if (!currentProvider.value) {
    ElMessage.warning('请先在 AI 配置中设置当前提供商')
    activeTab.value = 'config'
    return
  }

  analysisLoading.value = true
  const payload = {
    keyword_id: analysisKeywordId.value || null,
    article_ids: analysisArticleIds.value,
    model: null,
  }

  try {
    const res = await analysisApi.summary(payload)
    if (res.data.error) {
      ElMessage.error(res.data.error)
    } else {
      summaryResult.value = res.data
      lastSummaryResultId = null
      // 加载历史以获取记录 ID
      await loadHistory()
      // 找到最新的摘要记录
      if (summaryHistory.value.length > 0) {
        lastSummaryResultId = summaryHistory.value[0].id
      }
    }
  } catch (error) {
    if (error.response?.status === 403) {
      ElMessage.error('暂无权限使用此智能体，请联系管理员')
    } else if (error.response?.status === 429) {
      ElMessage.error(error.response.data?.detail || 'Token 用量已达上限')
    } else {
      ElMessage.error('分析请求失败')
    }
  } finally {
    analysisLoading.value = false
  }
}

async function loadHistory() {
  loadingHistory.value = true
  try {
    const res = await analysisApi.history(20)
    summaryHistory.value = res.data.filter(r => r.analysis_type === 'summary')
  } catch {
    // ignore
  } finally {
    loadingHistory.value = false
  }
}

function viewHistorySummary(row) {
  summaryResult.value = {
    summary: row.result?.summary || '',
    model: row.model,
    provider: '',
  }
  lastSummaryResultId = row.id
}

function closeSummaryResult() {
  summaryResult.value = null
  lastSummaryResultId = null
}

async function downloadSummary(format) {
  // 先找到最新的摘要记录 ID
  if (!lastSummaryResultId) {
    await loadHistory()
    if (summaryHistory.value.length > 0) {
      lastSummaryResultId = summaryHistory.value[0].id
    }
  }
  if (!lastSummaryResultId) {
    ElMessage.warning('未找到可下载的摘要记录')
    return
  }
  await doDownload(lastSummaryResultId, format)
}

async function downloadHistorySummary(row, format) {
  await doDownload(row.id, format)
}

async function doDownload(resultId, format) {
  try {
    const res = await analysisApi.downloadSummary(resultId, format)
    const blob = new Blob([res.data], { type: format === 'md' ? 'text/markdown' : 'application/msword' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = format === 'md' ? `summary_${resultId}.md` : `summary_${resultId}.doc`
    a.click()
    URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch {
    ElMessage.error('下载失败')
  }
}

function formatTime(time) {
  if (!time) return ''
  return new Date(time).toLocaleString('zh-CN')
}

function formatSummary(text) {
  return renderMarkdown(text)
}

// ========== 智能对话（会话管理）==========
const sessions = ref([])
const currentSessionId = ref(null)
const currentSession = ref(null)
const currentMessages = ref([])
const chatInput = ref('')
const chatLoading = ref(false)
const chatMessagesRef = ref(null)
const compressing = ref(false)

async function loadSessions() {
  try {
    const res = await chatSessionApi.list()
    sessions.value = res.data
  } catch {
    // ignore
  }
}

async function createSession() {
  if (!currentProvider.value) {
    ElMessage.warning('请先在 AI 配置中设置当前提供商')
    activeTab.value = 'config'
    return
  }
  try {
    const res = await chatSessionApi.create({
      title: '新对话',
      keyword_id: null,
      model: currentProvider.value.default_model,
    })
    sessions.value.unshift(res.data)
    await selectSession(res.data.id)
    ElMessage.success('已创建新对话')
  } catch {
    ElMessage.error('创建对话失败')
  }
}

async function selectSession(id) {
  currentSessionId.value = id
  try {
    const res = await chatSessionApi.get(id)
    currentSession.value = res.data
    currentMessages.value = res.data.messages || []
    await nextTick()
    scrollToBottom()
  } catch {
    ElMessage.error('加载对话失败')
  }
}

async function handleSessionCommand(cmd, session) {
  if (cmd === 'rename') {
    try {
      const { value } = await ElMessageBox.prompt('输入新的对话名称', '重命名', {
        inputValue: session.title,
        confirmButtonText: '确认',
        cancelButtonText: '取消',
      })
      if (value && value.trim()) {
        await chatSessionApi.update(session.id, { title: value.trim() })
        session.title = value.trim()
        if (currentSession.value?.id === session.id) {
          currentSession.value.title = value.trim()
        }
        ElMessage.success('已重命名')
      }
    } catch {
      // cancelled
    }
  } else if (cmd === 'delete') {
    try {
      await ElMessageBox.confirm(`确认删除对话「${session.title}」？所有消息和记忆将被清除。`, '提示', { type: 'warning' })
      await chatSessionApi.delete(session.id)
      sessions.value = sessions.value.filter(s => s.id !== session.id)
      if (currentSessionId.value === session.id) {
        currentSessionId.value = null
        currentSession.value = null
        currentMessages.value = []
      }
      ElMessage.success('已删除')
    } catch {
      // cancelled
    }
  }
}

async function sendChat() {
  if (!chatInput.value.trim() || !currentSession.value) return
  const userMsg = chatInput.value
  currentMessages.value.push({ role: 'user', content: userMsg })
  chatInput.value = ''
  chatLoading.value = true

  await nextTick()
  scrollToBottom()

  try {
    const res = await chatSessionApi.sendMessage(currentSession.value.id, {
      message: userMsg,
      model: currentSession.value.model,
    })
    if (res.data.error) {
      currentMessages.value.push({ role: 'assistant', content: '错误: ' + res.data.error })
    } else {
      currentMessages.value.push({
        role: 'assistant',
        content: res.data.reply,
        elapsed_ms: res.data.elapsed_ms,
        context_chars: res.data.context_chars,
      })
      // 更新模型信息
      if (res.data.model) {
        currentSession.value.model = res.data.model
      }
      // 如果触发了压缩，更新会话信息
      if (res.data.compressed) {
        await loadSessions()
        const updated = sessions.value.find(s => s.id === currentSession.value.id)
        if (updated) {
          updated.context_compressed = true
        }
      }
      // 更新标题和消息计数
      const sess = sessions.value.find(s => s.id === currentSession.value.id)
      if (sess) {
        if (sess.title === '新对话') {
          sess.title = userMsg.substring(0, 30) + (userMsg.length > 30 ? '...' : '')
          currentSession.value.title = sess.title
        }
        sess.message_count = (sess.message_count || 0) + 2
      }
    }
  } catch (error) {
    let errMsg = '请求失败，请重试'
    if (error.response?.status === 403) {
      errMsg = '暂无权限使用此智能体，请联系管理员'
    } else if (error.response?.status === 429) {
      errMsg = error.response.data?.detail || 'Token 用量已达上限，请明天再试'
    }
    currentMessages.value.push({ role: 'assistant', content: errMsg })
  } finally {
    chatLoading.value = false
    await nextTick()
    scrollToBottom()
  }
}

async function switchModel(newModel) {
  if (!currentSession.value) return
  try {
    await chatSessionApi.update(currentSession.value.id, { model: newModel })
    ElMessage.success(`已切换到模型: ${newModel}`)
  } catch {
    ElMessage.error('切换模型失败')
  }
}

async function updateSessionKeyword() {
  if (!currentSession.value) return
  try {
    await chatSessionApi.update(currentSession.value.id, { keyword_id: currentSession.value.keyword_id })
  } catch {
    // ignore
  }
}

async function compressContext() {
  if (!currentSession.value) return
  compressing.value = true
  try {
    const res = await chatSessionApi.compress(currentSession.value.id)
    currentSession.value.memory_summary = res.data.memory_summary
    currentSession.value.context_compressed = true
    const sess = sessions.value.find(s => s.id === currentSession.value.id)
    if (sess) {
      sess.context_compressed = true
    }
    ElMessage.success('上下文已压缩')
  } catch {
    ElMessage.error('压缩失败')
  } finally {
    compressing.value = false
  }
}

function scrollToBottom() {
  if (chatMessagesRef.value) {
    chatMessagesRef.value.scrollTop = chatMessagesRef.value.scrollHeight
  }
}

function formatChatMeta(message) {
  const seconds = (Number(message.elapsed_ms) / 1000).toFixed(1)
  const context = Number(message.context_chars || 0)
  return context > 0 ? `${seconds}s · 参考上下文 ${context} 字` : `${seconds}s · 未加载文章上下文`
}

// ========== 用量统计 ==========
const usageLoading = ref(false)
const usageData = ref({
  total_analysis: 0,
  by_type: { summary: 0, chat: 0, chart: 0, wordcloud: 0 },
  by_model: [],
  by_provider: [],
  total_sessions: 0,
  total_chat_messages: 0,
  total_tokens: 0,
  analysis_tokens: 0,
  chat_tokens: 0,
  daily: { labels: [], analysis: [], chat: [] },
})
const dailyChartRef = ref(null)
const modelChartRef = ref(null)
let dailyChartInstance = null
let modelChartInstance = null

const barColors = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9254de', '#36cfc9', '#ffc53d']

const typeBreakdown = computed(() => [
  { key: 'summary', label: '摘要分析', count: usageData.value.by_type.summary || 0, color: '#409eff' },
  { key: 'chat', label: '智能对话', count: usageData.value.by_type.chat || 0, color: '#67c23a' },
  { key: 'chart', label: '图表分析', count: usageData.value.by_type.chart || 0, color: '#e6a23c' },
  { key: 'wordcloud', label: '词云分析', count: usageData.value.by_type.wordcloud || 0, color: '#9254de' },
])

function formatTokens(n) {
  if (!n) return '0'
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'M'
  if (n >= 1_000) return (n / 1_000).toFixed(1) + 'K'
  return String(n)
}

function providerBarWidth(count) {
  const max = Math.max(...usageData.value.by_provider.map(p => p.count), 1)
  return Math.round((count / max) * 100)
}

async function loadUsageStats() {
  usageLoading.value = true
  try {
    const { data } = await analysisApi.usageStats()
    usageData.value = data
    await nextTick()
    renderDailyChart()
    renderModelChart()
  } catch {
    ElMessage.error('加载用量统计失败')
  } finally {
    usageLoading.value = false
  }
}

function renderDailyChart() {
  if (!dailyChartRef.value) return
  if (dailyChartInstance) dailyChartInstance.dispose()
  dailyChartInstance = echarts.init(dailyChartRef.value)
  dailyChartInstance.setOption({
    tooltip: { trigger: 'axis' },
    legend: { data: ['AI 分析', '对话消息'], bottom: 0, textStyle: { fontSize: 12 } },
    grid: { left: 40, right: 20, top: 20, bottom: 40 },
    xAxis: { type: 'category', data: usageData.value.daily.labels, axisLabel: { fontSize: 11 } },
    yAxis: { type: 'value', minInterval: 1, axisLabel: { fontSize: 11 } },
    series: [
      { name: 'AI 分析', type: 'bar', data: usageData.value.daily.analysis, itemStyle: { color: '#409eff', borderRadius: [4, 4, 0, 0] }, barWidth: '30%' },
      { name: '对话消息', type: 'bar', data: usageData.value.daily.chat, itemStyle: { color: '#67c23a', borderRadius: [4, 4, 0, 0] }, barWidth: '30%' },
    ],
  })
}

function renderModelChart() {
  if (!modelChartRef.value) return
  if (modelChartInstance) modelChartInstance.dispose()
  modelChartInstance = echarts.init(modelChartRef.value)
  const models = usageData.value.by_model
  modelChartInstance.setOption({
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { type: 'scroll', orient: 'vertical', right: 10, top: 'center', textStyle: { fontSize: 12 } },
    series: [{
      type: 'pie',
      radius: ['40%', '70%'],
      center: ['35%', '50%'],
      label: { show: false },
      data: models.map(m => ({ name: m.model, value: m.count })),
      itemStyle: { borderRadius: 4, borderColor: '#fff', borderWidth: 2 },
    }],
    color: barColors,
  })
}

// 切换到用量统计 tab 时加载数据
watch(activeTab, async (val) => {
  if (val === 'usage') {
    await loadUsageStats()
  }
  if (val === 'permission') {
    await loadPermissionData()
  }
})

// ========== 权限管理 ==========
const permLoading = ref(false)
const roles = ref([])
const userList = ref([])
const tokenUsageList = ref([])
const roleDialog = ref(false)
const roleForm = reactive({ id: null, name: '', description: '', daily_token_limit: 100000, monthly_token_limit: 3000000 })
const grantDialog = ref(false)
const currentGrantRole = ref(null)
const grantProviderList = ref([])
const assignDialog = ref(false)
const currentAssignUser = ref(null)
const selectedRoleIds = ref([])

async function loadPermissionData() {
  permLoading.value = true
  try {
    const [rolesRes, usersRes, usageRes] = await Promise.all([
      adminApi.listRoles(),
      adminApi.listUsers(),
      adminApi.getAllTokenUsage(),
    ])
    roles.value = rolesRes.data
    userList.value = usersRes.data
    tokenUsageList.value = usageRes.data
  } catch {
    ElMessage.error('加载权限数据失败')
  } finally {
    permLoading.value = false
  }
}

function openRoleDialog(row) {
  if (row) {
    Object.assign(roleForm, { id: row.id, name: row.name, description: row.description, daily_token_limit: row.daily_token_limit, monthly_token_limit: row.monthly_token_limit })
  } else {
    Object.assign(roleForm, { id: null, name: '', description: '', daily_token_limit: 100000, monthly_token_limit: 3000000 })
  }
  roleDialog.value = true
}

async function saveRole() {
  if (!roleForm.name.trim()) {
    ElMessage.warning('请输入角色名称')
    return
  }
  try {
    if (roleForm.id) {
      await adminApi.updateRole(roleForm.id, {
        name: roleForm.name,
        description: roleForm.description,
        daily_token_limit: roleForm.daily_token_limit,
        monthly_token_limit: roleForm.monthly_token_limit,
      })
      ElMessage.success('角色已更新')
    } else {
      await adminApi.createRole({
        name: roleForm.name,
        description: roleForm.description,
        daily_token_limit: roleForm.daily_token_limit,
        monthly_token_limit: roleForm.monthly_token_limit,
      })
      ElMessage.success('角色已创建')
    }
    roleDialog.value = false
    await loadPermissionData()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '保存失败'))
  }
}

async function deleteRole(row) {
  try {
    await ElMessageBox.confirm(`确认删除角色「${row.name}」？关联的用户和授权将一并清除。`, '提示', { type: 'warning' })
    await adminApi.deleteRole(row.id)
    ElMessage.success('已删除')
    await loadPermissionData()
  } catch (error) {
    if (error !== 'cancel') ElMessage.error(apiErrorMessage(error, '删除失败'))
  }
}

async function openGrantDialog(role) {
  currentGrantRole.value = role
  grantProviderList.value = []
  grantDialog.value = true
  try {
    const [providersRes, grantedIdsRes] = await Promise.all([
      providerApi.list(),
      adminApi.listRoleProviders(role.id),
    ])
    const grantedIds = new Set(grantedIdsRes.data)
    grantProviderList.value = providersRes.data.map(p => ({
      ...p,
      granted: grantedIds.has(p.id),
    }))
  } catch {
    ElMessage.error('加载授权信息失败')
  }
}

async function addGrant(provider) {
  try {
    await adminApi.createProviderGrant({ provider_id: provider.id, role_id: currentGrantRole.value.id })
    ElMessage.success(`已授权「${provider.name}」`)
    provider.granted = true
    await loadPermissionData()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '授权失败'))
  }
}

async function removeGrant(provider) {
  try {
    await adminApi.deleteProviderGrant(provider.id, currentGrantRole.value.id)
    ElMessage.success(`已撤销「${provider.name}」的授权`)
    provider.granted = false
    await loadPermissionData()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '撤销失败'))
  }
}

function openAssignDialog(user) {
  currentAssignUser.value = user
  selectedRoleIds.value = (user.roles || []).map(r => r.id)
  assignDialog.value = true
}

async function saveUserRoles() {
  try {
    // 先移除旧角色
    const oldRoleIds = (currentAssignUser.value.roles || []).map(r => r.id)
    for (const rid of oldRoleIds) {
      await adminApi.removeUserRole(currentAssignUser.value.id, rid)
    }
    // 再分配新角色
    if (selectedRoleIds.value.length > 0) {
      await adminApi.assignRoles({ user_ids: [currentAssignUser.value.id], role_id: selectedRoleIds.value[0] })
      for (let i = 1; i < selectedRoleIds.value.length; i++) {
        await adminApi.assignRoles({ user_ids: [currentAssignUser.value.id], role_id: selectedRoleIds.value[i] })
      }
    }
    ElMessage.success('角色分配已更新')
    assignDialog.value = false
    await loadPermissionData()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '分配失败'))
  }
}

async function removeUserRole(user, role) {
  try {
    await adminApi.removeUserRole(user.id, role.id)
    ElMessage.success(`已移除角色「${role.name}」`)
    await loadPermissionData()
  } catch (error) {
    ElMessage.error(apiErrorMessage(error, '移除失败'))
  }
}

// 普通用户设为当前模型
async function setCurrentForUser() {
  if (!formData.id) return
  try {
    await providerApi.setCurrent(formData.id)
    ElMessage.success('已设为当前模型')
    providerDrawer.value = false
    await loadPresets()
  } catch (error) {
    if (error.response?.status === 403) {
      ElMessage.error('暂无权限使用此智能体')
    } else {
      ElMessage.error('设置失败')
    }
  }
}

// ========== 生命周期 ==========
function handleResize() {
  dailyChartInstance?.resize()
  modelChartInstance?.resize()
}

onMounted(async () => {
  await loadPresets()
  await loadKeywords()
  await loadAnalysisArticles()
  await loadHistory()
  await loadSessions()
  window.addEventListener('resize', handleResize)
  // 检查路由参数
  const params = new URLSearchParams(window.location.search)
  const articleId = params.get('article_id')
  if (articleId) {
    activeTab.value = 'analysis'
    analysisArticleIds.value = [parseInt(articleId)]
  }
})

onBeforeUnmount(() => {
  cleanupPointerDrag()
  window.removeEventListener('resize', handleResize)
  dailyChartInstance?.dispose()
  modelChartInstance?.dispose()
})
</script>

<style scoped>
.ai-analysis { height: 100%; }

.config-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}
.config-info { font-size: 13px; color: #666; }
.config-info .separator { margin: 0 8px; color: #ccc; }
.text-warning { color: #e6a23c; }

.section-label {
  font-size: 14px;
  font-weight: 600;
  color: #1d1e1f;
  margin-bottom: 10px;
  padding-left: 8px;
  border-left: 3px solid #409eff;
}

.provider-col { margin-bottom: 12px; }
.provider-card {
  border: 1px solid #e8e8e8;
  border-radius: 8px;
  padding: 14px;
  cursor: pointer;
  transition: all 0.2s;
  background: #fff;
  height: 90px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.provider-card:hover { border-color: #409eff; box-shadow: 0 2px 12px rgba(64,158,255,0.12); }
.provider-card.dragging { opacity: 0.48; }
.provider-card.drag-over { border-color: #357c4b; box-shadow: inset 0 0 0 1px #357c4b; }
.provider-card.active { border-color: #67c23a; }
.provider-card.current { border-color: #409eff; background: #ecf5ff; }
.provider-card.local { background: #fafafa; }
.provider-card.custom { border-style: dashed; display: flex; align-items: center; justify-content: center; text-align: center; }

.provider-card-header { display: flex; justify-content: space-between; align-items: center; }
.provider-card-tools { display: flex; align-items: center; gap: 10px; }
.drag-handle { color: #a4aaa5; cursor: grab; touch-action: none; user-select: none; }
.drag-handle:active { cursor: grabbing; }
.provider-name { font-size: 14px; font-weight: 600; color: #1d1e1f; }
.provider-desc { font-size: 12px; color: #999; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.provider-type { font-size: 11px; color: #bbb; }

.status-dot { width: 8px; height: 8px; border-radius: 50%; }
.status-dot.configured { background: #67c23a; }
.status-dot.current { background: #409eff; box-shadow: 0 0 6px #409eff; }

.provider-detail { padding: 0 8px; }
.detail-desc { color: #999; font-size: 13px; margin-bottom: 16px; }
.detail-form .form-hint { font-size: 12px; color: #999; margin-top: 4px; }
.model-row { display: flex; gap: 8px; width: 100%; }
.detail-actions { display: flex; gap: 8px; margin-top: 20px; justify-content: flex-end; }

.analysis-control { margin-bottom: 16px; }
.result-card { margin-bottom: 16px; }
.result-header { display: flex; justify-content: space-between; align-items: center; }
.result-header-right { display: flex; align-items: center; gap: 8px; }
.action-row { display: flex; align-items: center; gap: 4px; flex-wrap: nowrap; }
.summary-content { line-height: 1.8; font-size: 14px; color: #333; }

/* 智能对话布局 */
.chat-layout {
  display: flex;
  height: calc(100vh - 180px);
  gap: 12px;
}

.chat-sidebar {
  width: 260px;
  flex-shrink: 0;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.chat-sidebar-header {
  padding: 12px;
  border-bottom: 1px solid #f0f0f0;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.15s;
  margin-bottom: 4px;
}

.session-item:hover { background: #f5f7fa; }
.session-item.active { background: #ecf5ff; border-left: 3px solid #409eff; }

.session-info { flex: 1; min-width: 0; }
.session-title {
  font-size: 13px;
  font-weight: 500;
  color: #1d1e1f;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.session-meta {
  font-size: 11px;
  color: #999;
  margin-top: 4px;
  display: flex;
  gap: 8px;
  align-items: center;
}
.memory-badge {
  background: #f0f9eb;
  color: #67c23a;
  padding: 1px 6px;
  border-radius: 8px;
  font-size: 10px;
}
.session-actions { flex-shrink: 0; }
.session-more {
  color: #ccc;
  cursor: pointer;
  font-size: 16px;
  transition: color 0.2s;
}
.session-more:hover { color: #409eff; }

.chat-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
  border-radius: 8px;
  border: 1px solid #e8e8e8;
  overflow: hidden;
}

.chat-header {
  padding: 12px 16px;
  border-bottom: 1px solid #f0f0f0;
}
.chat-header-info { display: flex; flex-direction: column; gap: 8px; }
.chat-title { font-size: 15px; font-weight: 600; color: #1d1e1f; }
.chat-model-bar { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
  background: #f5f7fa;
}

.chat-msg {
  margin-bottom: 16px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.chat-msg.user { flex-direction: row-reverse; }

.chat-avatar {
  width: 32px;
  height: 32px;
  border-radius: 6px;
  display: grid;
  place-items: center;
  font-size: 12px;
  font-weight: 600;
  background: #409eff;
  color: #fff;
  flex-shrink: 0;
}
.chat-avatar.user-avatar { background: #357c4b; }

.chat-bubble {
  max-width: 70%;
  padding: 10px 14px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.6;
}
.chat-msg.user .chat-bubble { white-space: pre-wrap; }
.chat-meta {
  margin-top: 7px;
  padding-top: 6px;
  border-top: 1px solid #ebeef5;
  color: #909399;
  font-size: 11px;
  line-height: 1.4;
}
.chat-msg.assistant .chat-bubble { background: #fff; border: 1px solid #e8e8e8; }
.chat-msg.user .chat-bubble { background: #409eff; color: #fff; }
.chat-bubble.loading { color: #999; font-style: italic; }

.chat-input {
  padding: 12px 16px;
  border-top: 1px solid #f0f0f0;
}

@media (max-width: 760px) {
  .chat-layout { flex-direction: column; height: auto; }
  .chat-sidebar { width: 100%; max-height: 200px; }
  .chat-main { min-height: 400px; }
  .chat-bubble { max-width: 85%; }
}

/* ========== Markdown 渲染样式 ========== */
.markdown-body { font-size: 14px; line-height: 1.7; word-break: break-word; }
.markdown-body :deep(h1) { font-size: 1.5em; font-weight: 700; margin: 0.8em 0 0.4em; padding-bottom: 0.3em; border-bottom: 1px solid #e8e8e8; }
.markdown-body :deep(h2) { font-size: 1.3em; font-weight: 700; margin: 0.8em 0 0.4em; padding-bottom: 0.3em; border-bottom: 1px solid #f0f0f0; }
.markdown-body :deep(h3) { font-size: 1.15em; font-weight: 600; margin: 0.7em 0 0.3em; }
.markdown-body :deep(h4) { font-size: 1em; font-weight: 600; margin: 0.6em 0 0.3em; }
.markdown-body :deep(h5) { font-size: 0.9em; font-weight: 600; margin: 0.6em 0 0.3em; }
.markdown-body :deep(h6) { font-size: 0.85em; font-weight: 600; margin: 0.6em 0 0.3em; color: #999; }
.markdown-body :deep(p) { margin: 0.5em 0; }
.markdown-body :deep(ul),
.markdown-body :deep(ol) { margin: 0.5em 0; padding-left: 1.5em; }
.markdown-body :deep(li) { margin: 0.2em 0; }
.markdown-body :deep(blockquote) {
  margin: 0.6em 0; padding: 0.4em 1em; border-left: 4px solid #409eff;
  background: rgba(64,158,255,0.06); color: #555; border-radius: 0 4px 4px 0;
}
.markdown-body :deep(blockquote p) { margin: 0.2em 0; }
.markdown-body :deep(code) {
  background: rgba(0,0,0,0.06); padding: 0.15em 0.4em; border-radius: 3px;
  font-size: 0.88em; font-family: 'Consolas','Monaco','Courier New',monospace; color: #c7254e;
}
.markdown-body :deep(.md-code-block) {
  margin: 0.6em 0; padding: 12px 14px; background: #1e1e2e; border-radius: 6px;
  overflow-x: auto; font-size: 13px; line-height: 1.5;
}
.markdown-body :deep(.md-code-block code) {
  background: none; color: #cdd6f4; padding: 0; font-size: inherit;
}
.markdown-body :deep(table) {
  width: 100%; border-collapse: collapse; margin: 0.6em 0; font-size: 0.9em;
}
.markdown-body :deep(th),
.markdown-body :deep(td) { border: 1px solid #e8e8e8; padding: 6px 10px; text-align: left; }
.markdown-body :deep(th) { background: #f5f7fa; font-weight: 600; }
.markdown-body :deep(tr:nth-child(even)) { background: #fafafa; }
.markdown-body :deep(hr) { border: none; border-top: 1px solid #e8e8e8; margin: 1em 0; }
.markdown-body :deep(a) { color: #409eff; text-decoration: none; }
.markdown-body :deep(a:hover) { text-decoration: underline; }
.markdown-body :deep(strong) { font-weight: 700; }
.markdown-body :deep(img) { max-width: 100%; border-radius: 4px; }

/* 用户气泡内 markdown 不需要代码块深色背景 */
.chat-msg.user .markdown-body :deep(code) { background: rgba(255,255,255,0.2); color: #fff; }

/* ========== 用量统计页面样式 ========== */
.usage-page { padding-bottom: 20px; }
.usage-overview { margin-bottom: 4px; }

.stat-card {
  display: flex; align-items: center; gap: 12px;
  padding: 16px; border-radius: 10px; color: #fff;
  transition: transform 0.2s, box-shadow 0.2s;
  min-height: 72px;
}
.stat-card:hover { transform: translateY(-2px); box-shadow: 0 4px 16px rgba(0,0,0,0.12); }
.stat-icon {
  width: 42px; height: 42px; border-radius: 10px;
  display: grid; place-items: center; font-size: 22px;
  background: rgba(255,255,255,0.2); flex-shrink: 0;
}
.stat-body { min-width: 0; }
.stat-value { font-size: 24px; font-weight: 700; line-height: 1.2; }
.stat-label { font-size: 12px; opacity: 0.85; margin-top: 2px; white-space: nowrap; }
.stat-blue { background: linear-gradient(135deg, #409eff, #5b8cff); }
.stat-green { background: linear-gradient(135deg, #67c23a, #85ce61); }
.stat-orange { background: linear-gradient(135deg, #e6a23c, #f0b050); }
.stat-purple { background: linear-gradient(135deg, #9254de, #b37feb); }

.usage-card { margin-bottom: 12px; }
.usage-card .card-title { font-size: 14px; font-weight: 600; color: #1d1e1f; }

.chart-container { width: 100%; height: 260px; }

.empty-tip { text-align: center; color: #ccc; padding: 40px 0; font-size: 13px; }

.type-list { display: flex; flex-direction: column; gap: 14px; padding: 8px 4px; }
.type-item { display: flex; align-items: center; gap: 10px; }
.type-dot { width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }
.type-name { font-size: 13px; color: #333; flex: 1; }
.type-count { font-size: 18px; font-weight: 700; color: #1d1e1f; }

.provider-list { display: flex; flex-direction: column; gap: 14px; padding: 8px 4px; }
.provider-bar-item { }
.provider-bar-header { display: flex; justify-content: space-between; margin-bottom: 6px; }
.provider-bar-name { font-size: 13px; color: #333; }
.provider-bar-count { font-size: 12px; color: #999; }
.provider-bar-track { width: 100%; height: 8px; background: #f0f0f0; border-radius: 4px; overflow: hidden; }
.provider-bar-fill { height: 100%; border-radius: 4px; transition: width 0.6s ease; }

/* ========== 权限管理页面样式 ========== */
.permission-page { padding-bottom: 20px; }
.perm-toolbar { margin-bottom: 12px; }
.perm-table { margin-bottom: 4px; }
.role-tag { margin-right: 4px; margin-bottom: 2px; }
.text-muted { color: #c0c4cc; font-size: 13px; }

.no-permission-tip { padding: 40px 0; }
.readonly-detail { margin-bottom: 16px; }
</style>
