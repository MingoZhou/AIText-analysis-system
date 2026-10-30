<template>
  <div class="collection-page">
    <el-tabs v-model="activeTab" class="page-tabs">
      <el-tab-pane name="sources">
        <template #label>
          <span class="tab-label"><el-icon><Connection /></el-icon>数据源</span>
        </template>

        <div class="toolbar">
          <div class="source-legend">
            <span><i class="dot official"></i>权威定向 {{ kindCount('official') }}</span>
            <span><i class="dot rss"></i>RSS/Atom {{ kindCount('rss') }}</span>
            <span><i class="dot search"></i>通用搜索 {{ kindCount('search') }}</span>
          </div>
          <el-button type="primary" :icon="Plus" @click="openSourceDialog()">新增数据源</el-button>
        </div>

        <el-table :data="sources" stripe row-key="id" empty-text="暂无数据源">
          <el-table-column label="类型" width="120">
            <template #default="{ row }">
              <el-tag :type="sourceKindType(row.source_kind)" effect="light">
                {{ sourceKindLabel(row.source_kind) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="name" label="名称" min-width="190" />
          <el-table-column label="站点 / 订阅地址" min-width="300" show-overflow-tooltip>
            <template #default="{ row }">{{ row.domain || row.base_url || '-' }}</template>
          </el-table-column>
          <el-table-column label="说明" min-width="240" show-overflow-tooltip>
            <template #default="{ row }">{{ row.config?.description || '-' }}</template>
          </el-table-column>
          <el-table-column prop="priority" label="优先级" width="85" align="center" />
          <el-table-column label="状态" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                v-model="row.is_active"
                inline-prompt
                active-text="开"
                inactive-text="停"
                @change="toggleSource(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="操作" width="130" :fixed="isMobile ? false : 'right'">
            <template #default="{ row }">
              <el-button link type="primary" :icon="Edit" @click="openSourceDialog(row)">编辑</el-button>
              <el-button link type="danger" :icon="Delete" @click="deleteSource(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane name="keywords">
        <template #label>
          <span class="tab-label"><el-icon><Key /></el-icon>关键词策略</span>
        </template>

        <div class="toolbar">
          <div class="toolbar-summary">
            <span>关键词 {{ keywords.length }}</span>
            <span>启用 {{ activeKeywordCount }}</span>
            <span>已选 {{ selectedKeywords.length }}</span>
          </div>
          <div class="toolbar-actions">
            <el-button :icon="Aim" :disabled="!selectedKeywords.length" @click="runSelected">
              采集选中
            </el-button>
            <el-button :icon="Promotion" :loading="collecting" @click="runAll">
              采集全部
            </el-button>
            <el-button type="primary" :icon="Plus" @click="openKeywordDialog()">
              新增关键词
            </el-button>
          </div>
        </div>

        <el-table
          :data="keywords"
          stripe
          row-key="id"
          empty-text="暂无关键词策略"
          @selection-change="selectedKeywords = $event"
        >
          <el-table-column type="selection" width="42" />
          <el-table-column label="核心关键词" min-width="140">
            <template #default="{ row }">
              <div class="primary-cell">
                <span class="primary-text">{{ row.keyword }}</span>
                <el-tag size="small" effect="plain">{{ row.category }}</el-tag>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="扩展策略" min-width="180">
            <template #default="{ row }">
              <div class="tag-list" v-if="strategyTags(row).length">
                <el-tag
                  v-for="tag in strategyTags(row).slice(0, 3)"
                  :key="tag.text + tag.type"
                  :type="tag.type"
                  size="small"
                  effect="light"
                >{{ tag.text }}</el-tag>
                <span v-if="strategyTags(row).length > 3" class="more-text">
                  +{{ strategyTags(row).length - 3 }}
                </span>
              </div>
              <span v-else class="muted">仅核心词</span>
            </template>
          </el-table-column>
          <el-table-column label="数据源" min-width="140" show-overflow-tooltip>
            <template #default="{ row }">
              <div class="source-list">
                <template v-if="row.source_ids?.length">
                  <span v-for="name in selectedSourceNames(row).slice(0, 2)" :key="name">{{ name }}</span>
                  <span v-if="selectedSourceNames(row).length > 2" class="muted">
                    等{{ selectedSourceNames(row).length }}个
                  </span>
                </template>
                <span v-else>全部启用源</span>
              </div>
            </template>
          </el-table-column>
          <el-table-column label="间隔" width="68" align="center">
            <template #default="{ row }">{{ row.crawl_interval }}h</template>
          </el-table-column>
          <el-table-column label="状态" width="70" align="center">
            <template #default="{ row }">
              <el-switch
                v-model="row.is_active"
                inline-prompt
                active-text="开"
                inactive-text="关"
                @change="toggleKeyword(row)"
              />
            </template>
          </el-table-column>
          <el-table-column label="邮件提醒" width="80" align="center">
            <template #default="{ row }">
              <el-switch
                v-model="row.notify_on_crawl"
                inline-prompt
                active-text="开"
                inactive-text="关"
                @change="toggleKeywordNotify(row)"
              />
            </template>
          </el-table-column>
          <el-table-column prop="article_count" label="文献" width="60" align="center" />
          <el-table-column label="最后采集" width="150">
            <template #default="{ row }"><span class="nowrap-cell">{{ formatTime(row.last_crawl_at, false) }}</span></template>
          </el-table-column>
          <el-table-column label="操作" width="170" :fixed="isMobile ? false : 'right'">
            <template #default="{ row }">
              <div class="action-row">
                <el-button link type="success" :icon="Promotion" @click="runKeyword(row)">采集</el-button>
                <el-button link type="primary" :icon="Edit" @click="openKeywordDialog(row)">编辑</el-button>
                <el-button link type="danger" :icon="Delete" @click="deleteKeyword(row)">删除</el-button>
              </div>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>

      <el-tab-pane name="logs">
        <template #label>
          <span class="tab-label"><el-icon><List /></el-icon>任务记录</span>
        </template>

        <div class="toolbar">
          <div class="toolbar-summary">
            <span>任务 {{ logs.length }}</span>
            <span>进行中 {{ runningCount }}</span>
            <span>新增文献 {{ logs.reduce((sum, row) => sum + row.saved_count, 0) }}</span>
          </div>
          <el-button :icon="Refresh" :loading="loadingLogs" @click="loadLogs">刷新</el-button>
        </div>

        <el-table :data="logs" stripe row-key="id" empty-text="暂无采集任务" @row-click="openLogDetail">
          <el-table-column prop="id" label="#" width="60" />
          <el-table-column prop="keyword_text" label="关键词" min-width="150" />
          <el-table-column label="状态" width="96" align="center">
            <template #default="{ row }">
              <el-tag :type="logStatusType(row.status)" effect="dark" size="small">
                {{ logStatusLabel(row.status) }}
              </el-tag>
            </template>
          </el-table-column>
          <el-table-column prop="found_count" label="发现" width="70" align="center" />
          <el-table-column prop="fetched_count" label="下载" width="70" align="center" />
          <el-table-column prop="parsed_count" label="解析" width="70" align="center" />
          <el-table-column prop="saved_count" label="新增" width="70" align="center">
            <template #default="{ row }">
              <span :class="{ positive: row.saved_count > 0 }">{{ row.saved_count }}</span>
            </template>
          </el-table-column>
          <el-table-column prop="duplicate_count" label="重复" width="70" align="center" />
          <el-table-column prop="rejected_count" label="低相关" width="78" align="center" />
          <el-table-column prop="failed_count" label="失败" width="70" align="center">
            <template #default="{ row }">
              <span :class="{ negative: row.failed_count > 0 }">{{ row.failed_count }}</span>
            </template>
          </el-table-column>
          <el-table-column label="开始时间" width="160">
            <template #default="{ row }">{{ formatTime(row.started_at) }}</template>
          </el-table-column>
          <el-table-column label="耗时" width="90" align="center">
            <template #default="{ row }">{{ formatDuration(row.duration) }}</template>
          </el-table-column>
          <el-table-column label="明细" width="76" :fixed="isMobile ? false : 'right'" align="center">
            <template #default="{ row }">
              <el-button link type="primary" :icon="View" @click.stop="openLogDetail(row)">查看</el-button>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="76" :fixed="isMobile ? false : 'right'" align="center">
            <template #default="{ row }">
              <el-button link type="danger" :icon="Delete" @click.stop="deleteLog(row)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>
      </el-tab-pane>
    </el-tabs>

    <el-dialog
      v-model="keywordDialogVisible"
      :title="editingKeywordId ? '编辑关键词策略' : '新增关键词策略'"
      width="760px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form ref="keywordFormRef" :model="keywordForm" :rules="keywordRules" label-width="100px">
        <div class="form-grid">
          <el-form-item label="核心关键词" prop="keyword">
            <el-input v-model="keywordForm.keyword" maxlength="100" />
          </el-form-item>
          <el-form-item label="分类" prop="category">
            <el-select v-model="keywordForm.category" class="full-width">
              <el-option v-for="item in categories" :key="item" :label="item" :value="item" />
            </el-select>
          </el-form-item>
          <el-form-item label="采集间隔" prop="crawl_interval">
            <el-input-number v-model="keywordForm.crawl_interval" :min="1" :max="720" />
            <span class="unit">小时</span>
          </el-form-item>
          <el-form-item label="时间范围" prop="date_range_days">
            <el-select v-model="keywordForm.date_range_days" class="full-width">
              <el-option label="最近1天" :value="1" />
              <el-option label="最近3天" :value="3" />
              <el-option label="最近7天" :value="7" />
              <el-option label="最近15天" :value="15" />
              <el-option label="最近30天" :value="30" />
              <el-option label="最近90天" :value="90" />
              <el-option label="不限" :value="0" />
            </el-select>
          </el-form-item>
          <el-form-item label="启用状态">
            <el-switch v-model="keywordForm.is_active" active-text="启用" inactive-text="停用" />
          </el-form-item>
        </div>

        <el-form-item label="扩展词">
          <el-select
            v-model="keywordForm.aliases"
            multiple
            filterable
            allow-create
            default-first-option
            class="full-width"
            placeholder="输入后按回车添加"
          />
        </el-form-item>
        <el-form-item label="精确短语">
          <el-select
            v-model="keywordForm.exact_phrases"
            multiple
            filterable
            allow-create
            default-first-option
            class="full-width"
            placeholder="输入完整短语后按回车添加"
          />
        </el-form-item>
        <el-form-item label="排除词">
          <el-select
            v-model="keywordForm.excluded_terms"
            multiple
            filterable
            allow-create
            default-first-option
            class="full-width"
            placeholder="输入后按回车添加"
          />
        </el-form-item>
        <el-form-item label="限定站点">
          <el-select
            v-model="keywordForm.site_filters"
            multiple
            filterable
            allow-create
            default-first-option
            class="full-width"
            placeholder="例如 caict.ac.cn；留空不限制"
          />
        </el-form-item>
        <el-form-item label="选择数据源">
          <el-select
            v-model="keywordForm.source_ids"
            multiple
            collapse-tags
            collapse-tags-tooltip
            class="full-width"
            placeholder="留空使用全部启用数据源"
          >
            <el-option-group
              v-for="group in sourceGroups"
              :key="group.kind"
              :label="group.label"
            >
              <el-option v-for="source in group.items" :key="source.id" :label="source.name" :value="source.id" />
            </el-option-group>
          </el-select>
        </el-form-item>

        <el-form-item label="查询预览">
          <div class="preview-wrap">
            <el-button :icon="Search" :loading="previewLoading" @click="previewQueries">生成预览</el-button>
            <div v-if="queryPreview.length" class="query-preview">
              <div v-for="query in queryPreview.slice(0, 8)" :key="query.source_id + query.query">
                <span>{{ query.source_name }}</span>
                <code>{{ query.display_query || query.query }}</code>
              </div>
            </div>
          </div>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="keywordDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submittingKeyword" @click="saveKeyword">保存</el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="sourceDialogVisible"
      :title="editingSourceId ? '编辑数据源' : '新增数据源'"
      width="620px"
      :close-on-click-modal="false"
      destroy-on-close
    >
      <el-form ref="sourceFormRef" :model="sourceForm" :rules="sourceRules" label-width="110px">
        <el-form-item label="名称" prop="name">
          <el-input v-model="sourceForm.name" maxlength="100" />
        </el-form-item>
        <el-form-item label="来源类型" prop="source_kind">
          <el-segmented v-model="sourceForm.source_kind" :options="sourceKindOptions" />
        </el-form-item>
        <el-form-item :label="sourceForm.source_kind === 'rss' ? '订阅地址' : '站点地址'" prop="base_url">
          <el-input v-model="sourceForm.base_url" placeholder="https://" />
        </el-form-item>
        <el-form-item v-if="sourceForm.source_kind === 'official'" label="限定域名" prop="domain">
          <el-input v-model="sourceForm.domain" placeholder="例如 miit.gov.cn" />
        </el-form-item>
        <el-form-item label="优先级" prop="priority">
          <el-input-number v-model="sourceForm.priority" :min="1" :max="999" />
          <span class="unit">数值越小越优先</span>
        </el-form-item>
        <el-form-item label="说明">
          <el-input v-model="sourceForm.description" type="textarea" :rows="3" maxlength="300" show-word-limit />
        </el-form-item>
        <el-form-item label="启用状态">
          <el-switch v-model="sourceForm.is_active" active-text="启用" inactive-text="停用" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="sourceDialogVisible = false">取消</el-button>
        <el-button type="primary" :loading="submittingSource" @click="saveSource">保存</el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="logDrawerVisible" title="采集任务明细" size="64%" destroy-on-close>
      <template v-if="currentLog">
        <div class="log-overview">
          <div><span>关键词</span><strong>{{ currentLog.keyword_text }}</strong></div>
          <div><span>状态</span><el-tag :type="logStatusType(currentLog.status)">{{ logStatusLabel(currentLog.status) }}</el-tag></div>
          <div><span>发现 / 新增</span><strong>{{ currentLog.found_count }} / {{ currentLog.saved_count }}</strong></div>
          <div><span>耗时</span><strong>{{ formatDuration(currentLog.duration) }}</strong></div>
        </div>
        <el-alert
          v-if="currentLog.error_message"
          :title="currentLog.error_message"
          type="warning"
          :closable="false"
          show-icon
          class="error-alert"
        />
        <el-table v-loading="loadingItems" :data="logItems" stripe empty-text="暂无URL处理记录">
          <el-table-column label="来源" width="145" show-overflow-tooltip>
            <template #default="{ row }">{{ sourceMap.get(row.source_id)?.name || '-' }}</template>
          </el-table-column>
          <el-table-column prop="title" label="标题" min-width="260" show-overflow-tooltip />
          <el-table-column label="状态" width="100">
            <template #default="{ row }">
              <el-tag :type="itemStatusType(row.status)" size="small">{{ itemStatusLabel(row.status) }}</el-tag>
            </template>
          </el-table-column>
          <el-table-column label="阶段" width="110">
            <template #default="{ row }">{{ stageLabel(row.stage) }}</template>
          </el-table-column>
          <el-table-column prop="http_status" label="HTTP" width="72" align="center" />
          <el-table-column label="错误" min-width="220" show-overflow-tooltip>
            <template #default="{ row }">{{ row.error_message || '-' }}</template>
          </el-table-column>
          <el-table-column label="链接" width="72" :fixed="isMobile ? false : 'right'">
            <template #default="{ row }">
              <el-link :href="row.url" target="_blank" type="primary" :underline="false">
                <el-icon><Link /></el-icon>
              </el-link>
            </template>
          </el-table-column>
        </el-table>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Aim, Connection, Delete, Edit, Key, Link, List, Plus,
  Promotion, Refresh, Search, View,
} from '@element-plus/icons-vue'
import { crawlerApi, keywordApi, sourceApi } from '../api'

const activeTab = ref('sources')
const keywords = ref([])
const sources = ref([])
const logs = ref([])
const selectedKeywords = ref([])
const collecting = ref(false)
const loadingLogs = ref(false)
const isMobile = ref(window.innerWidth <= 760)
const updateMobileState = () => { isMobile.value = window.innerWidth <= 760 }

const sourceMap = computed(() => new Map(sources.value.map((source) => [source.id, source])))
const activeKeywordCount = computed(() => keywords.value.filter((item) => item.is_active).length)
const runningCount = computed(() => logs.value.filter((item) => ['pending', 'running'].includes(item.status)).length)
const sourceGroups = computed(() => [
  { kind: 'official', label: '权威定向来源', items: sources.value.filter((item) => item.source_kind === 'official' && item.is_active) },
  { kind: 'rss', label: 'RSS / Atom', items: sources.value.filter((item) => item.source_kind === 'rss' && item.is_active) },
  { kind: 'search', label: '通用搜索', items: sources.value.filter((item) => item.source_kind === 'search' && item.is_active) },
].filter((group) => group.items.length))

const categories = ['通用', '政策', '技术', '标准', '产业', '市场']
const sourceKindOptions = [
  { label: '权威定向', value: 'official' },
  { label: 'RSS/Atom', value: 'rss' },
  { label: '通用搜索', value: 'search' },
]

const loadKeywords = async () => {
  const { data } = await keywordApi.list()
  keywords.value = data
}

const loadSources = async () => {
  const { data } = await sourceApi.list()
  sources.value = data
}

const loadLogs = async () => {
  loadingLogs.value = true
  try {
    const { data } = await crawlerApi.getLogs(50)
    logs.value = data
    if (!data.some((item) => ['pending', 'running'].includes(item.status))) {
      await loadKeywords()
    }
  } catch (error) {
    ElMessage.error('加载任务记录失败')
  } finally {
    loadingLogs.value = false
  }
}

const strategyTags = (row) => [
  ...(row.aliases || []).map((text) => ({ text, type: 'success' })),
  ...(row.exact_phrases || []).map((text) => ({ text: `“${text}”`, type: 'primary' })),
  ...(row.excluded_terms || []).map((text) => ({ text: `排除:${text}`, type: 'danger' })),
  ...(row.site_filters || []).map((text) => ({ text: `站点:${text}`, type: 'warning' })),
]

const selectedSourceNames = (row) => (row.source_ids || [])
  .map((id) => sourceMap.value.get(id)?.name)
  .filter(Boolean)

const sourceKindLabel = (kind) => ({ official: '权威定向', rss: 'RSS/Atom', search: '通用搜索' }[kind] || kind)
const sourceKindType = (kind) => ({ official: 'success', rss: 'warning', search: 'info' }[kind] || 'info')
const kindCount = (kind) => sources.value.filter((item) => item.source_kind === kind).length

const logStatusLabel = (status) => ({
  pending: '等待中', running: '采集中', success: '成功', partial: '部分成功',
  empty: '无新结果', blocked: '被限制', failed: '失败',
}[status] || status)
const logStatusType = (status) => ({
  pending: 'info', running: 'warning', success: 'success', partial: 'warning',
  empty: 'info', blocked: 'danger', failed: 'danger',
}[status] || 'info')

const itemStatusLabel = (status) => ({
  discovered: '已发现', saved: '已保存', duplicate: '重复', rejected: '低相关',
  blocked: '被限制', failed: '失败',
}[status] || status)
const itemStatusType = (status) => ({
  saved: 'success', duplicate: 'info', rejected: 'warning', blocked: 'danger', failed: 'danger',
}[status] || 'info')
const stageLabel = (stage) => ({
  discovery: '发现', fetch: '下载', parse: '解析', relevance: '相关性',
  deduplication: '去重', persistence: '入库',
}[stage] || stage || '-')

const pad = (value) => String(value).padStart(2, '0')
const formatTime = (value, withSeconds = true) => {
  if (!value) return '-'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  const base = `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`
  return withSeconds ? `${base}:${pad(date.getSeconds())}` : base
}
const formatDuration = (value) => {
  if (value === null || value === undefined) return '-'
  if (value < 1) return `${Math.round(value * 1000)}ms`
  if (value < 60) return `${value.toFixed(1)}s`
  return `${Math.floor(value / 60)}m${Math.round(value % 60)}s`
}

const keywordDialogVisible = ref(false)
const editingKeywordId = ref(null)
const keywordFormRef = ref(null)
const submittingKeyword = ref(false)
const previewLoading = ref(false)
const queryPreview = ref([])
const keywordForm = reactive({
  keyword: '', category: '通用', is_active: true, crawl_interval: 24,
  date_range_days: 7,
  aliases: [], exact_phrases: [], excluded_terms: [], site_filters: [], source_ids: [],
  notify_on_crawl: true,
})
const keywordRules = {
  keyword: [{ required: true, message: '请输入核心关键词', trigger: 'blur' }],
  category: [{ required: true, message: '请选择分类', trigger: 'change' }],
  crawl_interval: [{ required: true, message: '请输入采集间隔', trigger: 'blur' }],
}

const resetKeywordForm = () => Object.assign(keywordForm, {
  keyword: '', category: '通用', is_active: true, crawl_interval: 24,
  date_range_days: 7,
  aliases: [], exact_phrases: [], excluded_terms: [], site_filters: [], source_ids: [],
  notify_on_crawl: true,
})

const openKeywordDialog = (row = null) => {
  resetKeywordForm()
  queryPreview.value = []
  editingKeywordId.value = row?.id || null
  if (row) {
    Object.assign(keywordForm, {
      keyword: row.keyword,
      category: row.category,
      is_active: row.is_active,
      crawl_interval: row.crawl_interval,
      date_range_days: row.date_range_days ?? 7,
      aliases: [...(row.aliases || [])],
      exact_phrases: [...(row.exact_phrases || [])],
      excluded_terms: [...(row.excluded_terms || [])],
      site_filters: [...(row.site_filters || [])],
      source_ids: [...(row.source_ids || [])],
      notify_on_crawl: row.notify_on_crawl !== false,
    })
  }
  keywordDialogVisible.value = true
}

const keywordPayload = () => ({
  keyword: keywordForm.keyword.trim(),
  category: keywordForm.category,
  is_active: keywordForm.is_active,
  crawl_interval: keywordForm.crawl_interval,
  date_range_days: keywordForm.date_range_days,
  aliases: keywordForm.aliases,
  exact_phrases: keywordForm.exact_phrases,
  excluded_terms: keywordForm.excluded_terms,
  site_filters: keywordForm.site_filters,
  source_ids: keywordForm.source_ids,
  notify_on_crawl: keywordForm.notify_on_crawl,
})

const previewQueries = async () => {
  if (!keywordForm.keyword.trim()) {
    ElMessage.warning('请先填写核心关键词')
    return
  }
  previewLoading.value = true
  try {
    const { data } = await keywordApi.preview(keywordPayload())
    queryPreview.value = data.queries || []
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '查询策略生成失败')
  } finally {
    previewLoading.value = false
  }
}

const saveKeyword = async () => {
  try {
    await keywordFormRef.value.validate()
  } catch {
    return
  }
  submittingKeyword.value = true
  try {
    if (editingKeywordId.value) {
      await keywordApi.update(editingKeywordId.value, keywordPayload())
    } else {
      await keywordApi.create(keywordPayload())
    }
    keywordDialogVisible.value = false
    await loadKeywords()
    ElMessage.success('关键词策略已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    submittingKeyword.value = false
  }
}

const toggleKeyword = async (row) => {
  try {
    await keywordApi.update(row.id, { is_active: row.is_active })
  } catch {
    row.is_active = !row.is_active
    ElMessage.error('状态更新失败')
  }
}

const toggleKeywordNotify = async (row) => {
  try {
    await keywordApi.update(row.id, { notify_on_crawl: row.notify_on_crawl })
  } catch {
    row.notify_on_crawl = !row.notify_on_crawl
    ElMessage.error('邮件提醒设置失败')
  }
}

const deleteKeyword = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除关键词策略“${row.keyword}”吗？`, '删除确认', { type: 'warning' })
    await keywordApi.delete(row.id)
    await loadKeywords()
    ElMessage.success('已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败')
  }
}

const runCrawl = async (keywordIds) => {
  collecting.value = true
  try {
    const { data } = await crawlerApi.run({ keyword_ids: keywordIds, source_ids: [], force: false })
    ElMessage.success(data.message)
    activeTab.value = 'logs'
    await loadLogs()
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '采集任务创建失败')
  } finally {
    collecting.value = false
  }
}

const runAll = async () => {
  if (!activeKeywordCount.value) return ElMessage.warning('没有启用的关键词')
  try {
    await ElMessageBox.confirm('确定采集全部已启用关键词吗？', '采集确认', { type: 'info' })
    await runCrawl([])
  } catch {}
}
const runSelected = () => runCrawl(selectedKeywords.value.map((item) => item.id))
const runKeyword = (row) => runCrawl([row.id])

const sourceDialogVisible = ref(false)
const editingSourceId = ref(null)
const sourceFormRef = ref(null)
const submittingSource = ref(false)
const sourceForm = reactive({
  name: '', source_kind: 'official', base_url: '', domain: '', priority: 50,
  is_active: true, description: '',
})
const sourceRules = {
  name: [{ required: true, message: '请输入数据源名称', trigger: 'blur' }],
  source_kind: [{ required: true, message: '请选择来源类型', trigger: 'change' }],
  base_url: [{ required: true, message: '请输入地址', trigger: 'blur' }],
}

const resetSourceForm = () => Object.assign(sourceForm, {
  name: '', source_kind: 'official', base_url: '', domain: '', priority: 50,
  is_active: true, description: '',
})
const openSourceDialog = (row = null) => {
  resetSourceForm()
  editingSourceId.value = row?.id || null
  if (row) Object.assign(sourceForm, {
    name: row.name,
    source_kind: row.source_kind,
    base_url: row.base_url,
    domain: row.domain,
    priority: row.priority,
    is_active: row.is_active,
    description: row.config?.description || '',
  })
  sourceDialogVisible.value = true
}
const sourcePayload = () => ({
  name: sourceForm.name.trim(),
  source_kind: sourceForm.source_kind,
  base_url: sourceForm.base_url.trim(),
  domain: sourceForm.domain.trim(),
  priority: sourceForm.priority,
  is_active: sourceForm.is_active,
  config: { description: sourceForm.description.trim() },
})
const saveSource = async () => {
  try {
    await sourceFormRef.value.validate()
  } catch {
    return
  }
  submittingSource.value = true
  try {
    if (editingSourceId.value) await sourceApi.update(editingSourceId.value, sourcePayload())
    else await sourceApi.create(sourcePayload())
    sourceDialogVisible.value = false
    await loadSources()
    ElMessage.success('数据源已保存')
  } catch (error) {
    ElMessage.error(error?.response?.data?.detail || '保存失败')
  } finally {
    submittingSource.value = false
  }
}
const toggleSource = async (row) => {
  try {
    await sourceApi.update(row.id, { is_active: row.is_active })
  } catch {
    row.is_active = !row.is_active
    ElMessage.error('状态更新失败')
  }
}
const deleteSource = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除数据源“${row.name}”吗？`, '删除确认', { type: 'warning' })
    await sourceApi.delete(row.id)
    await Promise.all([loadSources(), loadKeywords()])
    ElMessage.success('已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败')
  }
}

const deleteLog = async (row) => {
  try {
    await ElMessageBox.confirm(`确定删除任务记录 #${row.id} 吗？`, '删除确认', { type: 'warning' })
    await crawlerApi.deleteLog(row.id)
    await loadLogs()
    ElMessage.success('已删除')
  } catch (error) {
    if (error !== 'cancel' && error !== 'close') ElMessage.error('删除失败')
  }
}

const logDrawerVisible = ref(false)
const currentLog = ref(null)
const logItems = ref([])
const loadingItems = ref(false)
const openLogDetail = async (row) => {
  currentLog.value = row
  logDrawerVisible.value = true
  loadingItems.value = true
  try {
    const { data } = await crawlerApi.getItems(row.id)
    logItems.value = data
  } catch {
    ElMessage.error('加载任务明细失败')
  } finally {
    loadingItems.value = false
  }
}

let pollTimer = null
onMounted(async () => {
  window.addEventListener('resize', updateMobileState)
  try {
    await Promise.all([loadSources(), loadKeywords(), loadLogs()])
  } catch {
    ElMessage.error('采集配置加载失败')
  }
  pollTimer = setInterval(() => {
    if (activeTab.value === 'logs' || runningCount.value) loadLogs()
  }, 5000)
})
onBeforeUnmount(() => {
  window.removeEventListener('resize', updateMobileState)
  if (pollTimer) clearInterval(pollTimer)
})
</script>

<style scoped>
.collection-page {
  min-width: 0;
}

.page-tabs :deep(.el-tabs__header) {
  margin-bottom: 16px;
}

.tab-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  margin-bottom: 14px;
  min-height: 34px;
}

.toolbar-summary,
.source-legend,
.toolbar-actions {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
}

.toolbar-summary,
.source-legend {
  color: var(--el-text-color-secondary);
  font-size: 13px;
}

.primary-cell,
.source-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 7px;
}

.primary-text {
  color: var(--el-text-color-primary);
  font-weight: 500;
}

.tag-list {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 5px;
}

.source-list span:not(.muted) {
  max-width: 135px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.muted,
.more-text,
.unit {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.unit {
  margin-left: 8px;
}

.positive {
  color: var(--el-color-success);
  font-weight: 500;
}

.negative {
  color: var(--el-color-danger);
  font-weight: 500;
}

.dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  margin-right: 5px;
  border-radius: 50%;
}

.dot.official { background: var(--el-color-success); }
.dot.rss { background: var(--el-color-warning); }
.dot.search { background: var(--el-color-info); }

.form-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  column-gap: 22px;
}

.full-width,
.preview-wrap {
  width: 100%;
}

.query-preview {
  display: grid;
  gap: 7px;
  margin-top: 10px;
}

.query-preview > div {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.query-preview span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.query-preview code {
  min-width: 0;
  overflow-wrap: anywhere;
  color: var(--el-text-color-primary);
  background: var(--el-fill-color-light);
  padding: 5px 7px;
  border-radius: 4px;
}

.log-overview {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.log-overview > div {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.log-overview span {
  color: var(--el-text-color-secondary);
  font-size: 12px;
}

.log-overview strong {
  font-weight: 500;
}

.error-alert {
  margin-bottom: 16px;
}

:deep(.el-table__row) {
  cursor: default;
}

.action-row {
  display: flex;
  align-items: center;
  gap: 4px;
  flex-wrap: nowrap;
  white-space: nowrap;
}

.nowrap-cell {
  white-space: nowrap;
}

@media (max-width: 760px) {
  .toolbar {
    align-items: flex-start;
    flex-direction: column;
  }

  .form-grid,
  .log-overview {
    grid-template-columns: 1fr;
  }

  .query-preview > div {
    grid-template-columns: 1fr;
  }
}
</style>
