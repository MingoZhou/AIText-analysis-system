<template>
  <div class="collected-info">
    <!-- 顶部筛选栏 -->
    <el-card class="filter-card" shadow="never">
      <div class="filter-bar">
        <div class="filter-item">
          <span class="filter-label">关键词</span>
          <el-select
            v-model="filters.keyword_id"
            placeholder="全部关键词"
            clearable
            filterable
            style="width: 200px"
            @change="handleSearch"
          >
            <el-option
              v-for="kw in keywordOptions"
              :key="kw.id"
              :label="kw.keyword"
              :value="kw.id"
            />
          </el-select>
        </div>

        <div class="filter-item">
          <span class="filter-label">类型</span>
          <el-select
            v-model="filters.source_type"
            placeholder="全部类型"
            clearable
            style="width: 150px"
            @change="handleSearch"
          >
            <el-option label="政策" value="policy" />
            <el-option label="资讯" value="news" />
            <el-option label="文档" value="document" />
            <el-option label="PDF" value="pdf" />
          </el-select>
        </div>

        <div class="filter-item filter-search">
          <span class="filter-label">搜索</span>
          <el-input
            v-model="filters.search"
            placeholder="输入标题关键词搜索"
            clearable
            style="width: 240px"
            @keyup.enter="handleSearch"
            @clear="handleSearch"
          >
            <template #prefix>
              <el-icon><Search /></el-icon>
            </template>
          </el-input>
        </div>

        <div class="filter-item">
          <span class="filter-label">仅看收藏</span>
          <el-switch v-model="filters.is_starred" @change="handleSearch" />
        </div>

        <div class="filter-item filter-actions">
          <el-button type="primary" :icon="Search" @click="handleSearch">查询</el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </div>
      </div>
    </el-card>

    <!-- 文章列表 -->
    <el-card class="table-card" shadow="never">
      <template #header>
        <div class="table-header">
          <span class="table-title">
            <el-icon><Document /></el-icon>
            文章列表
          </span>
          <span class="table-total">共 {{ pagination.total }} 条</span>
        </div>
      </template>

      <el-table
        v-loading="loading"
        :data="tableData"
        stripe
        highlight-current-row
        style="width: 100%"
        :header-cell-style="{ background: '#fafafa', color: '#333', fontWeight: 600 }"
        @row-click="handleRowClick"
      >
        <el-table-column label="标题" min-width="280" show-overflow-tooltip>
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              class="title-link"
              @click.stop="openDetail(row)"
            >
              <el-icon v-if="row.is_starred" class="star-icon"><StarFilled /></el-icon>
              {{ row.title }}
            </el-button>
          </template>
        </el-table-column>

        <el-table-column label="关键词" width="130" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="row.keyword_text" type="info" effect="plain" size="small">
              {{ row.keyword_text }}
            </el-tag>
            <span v-else class="text-muted">-</span>
          </template>
        </el-table-column>

        <el-table-column label="来源" width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.source_name || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="类型" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.source_type)" effect="light" size="small">
              {{ typeText(row.source_type) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="发布日期" width="120" align="center">
          <template #default="{ row }">
            <span>{{ row.publish_date || '-' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="采集时间" width="170" align="center">
          <template #default="{ row }">
            <span>{{ formatDateTime(row.crawl_date) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="230" :fixed="isMobile ? false : 'right'" align="center">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              size="small"
              :icon="View"
              @click.stop="openDetail(row)"
            >详情</el-button>

            <el-button
              v-if="isPdf(row)"
              type="success"
              link
              size="small"
              :icon="Download"
              :loading="downloadingId === row.id"
              @click.stop="handleDownload(row)"
            >下载</el-button>

            <el-button
              type="warning"
              link
              size="small"
              :icon="row.is_starred ? StarFilled : Star"
              @click.stop="handleToggleStar(row)"
            >{{ row.is_starred ? '已藏' : '收藏' }}</el-button>

            <el-button
              type="danger"
              link
              size="small"
              :icon="Delete"
              @click.stop="handleDelete(row)"
            >删除</el-button>
          </template>
        </el-table-column>

        <template #empty>
          <el-empty description="暂无文章数据" :image-size="120" />
        </template>
      </el-table>

      <!-- 分页 -->
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="pagination.page"
          v-model:page-size="pagination.page_size"
          :total="pagination.total"
          :page-sizes="[10, 20, 50, 100]"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @size-change="handleSizeChange"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 文章详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="文章详情"
      direction="rtl"
      size="50%"
      :destroy-on-close="true"
    >
      <div v-loading="detailLoading" class="detail-content">
        <template v-if="currentArticle">
          <h2 class="detail-title">{{ currentArticle.title }}</h2>

          <div class="detail-meta">
            <div class="meta-row">
              <span class="meta-label">来源：</span>
              <el-link
                v-if="currentArticle.source_url"
                type="primary"
                :href="currentArticle.source_url"
                target="_blank"
                :underline="false"
              >
                {{ currentArticle.source_name || currentArticle.source_url }}
                <el-icon class="link-icon"><Link /></el-icon>
              </el-link>
              <span v-else>{{ currentArticle.source_name || '-' }}</span>
            </div>

            <div class="meta-row">
              <span class="meta-label">作者：</span>
              <span>{{ currentArticle.author || '未知' }}</span>
            </div>

            <div class="meta-row">
              <span class="meta-label">类型：</span>
              <el-tag :type="typeTagType(currentArticle.source_type)" effect="light" size="small">
                {{ typeText(currentArticle.source_type) }}
              </el-tag>
            </div>

            <div class="meta-row">
              <span class="meta-label">发布日期：</span>
              <span>{{ currentArticle.publish_date || '-' }}</span>
            </div>

            <div class="meta-row">
              <span class="meta-label">采集时间：</span>
              <span>{{ formatDateTime(currentArticle.crawl_date) }}</span>
            </div>

            <div class="meta-row" v-if="currentArticle.keyword_text">
              <span class="meta-label">关键词：</span>
              <el-tag type="info" effect="plain" size="small">
                {{ currentArticle.keyword_text }}
              </el-tag>
            </div>
          </div>

          <template v-if="currentArticle.extra_metadata?.attachments?.length">
            <el-divider content-position="left">相关附件</el-divider>
            <div class="attachment-list">
              <div
                v-for="attachment in currentArticle.extra_metadata.attachments"
                :key="attachment.url"
                class="attachment-item"
              >
                <el-link :href="attachment.url" target="_blank" type="primary" :underline="false">
                  <el-icon><Document /></el-icon>
                  <span>{{ attachment.title || '查看附件' }}</span>
                  <el-icon><Link /></el-icon>
                </el-link>
                <el-tag v-if="attachment.archive_status === 'saved'" type="success" size="small" effect="plain">
                  已归档
                </el-tag>
                <el-tag v-else-if="attachment.archive_status === 'failed'" type="warning" size="small" effect="plain">
                  仅保留链接
                </el-tag>
              </div>
            </div>
          </template>

          <el-divider content-position="left">正文内容</el-divider>

          <div class="detail-body">
            <pre>{{ currentArticle.content || '暂无正文内容' }}</pre>
          </div>
        </template>
      </div>

      <template #footer>
        <div class="drawer-footer" v-if="currentArticle">
          <el-button
            v-if="isPdf(currentArticle)"
            type="success"
            :icon="Download"
            :loading="downloadingId === currentArticle.id"
            @click="handleDownload(currentArticle)"
          >下载PDF</el-button>

          <el-button
            type="warning"
            :icon="currentArticle.is_starred ? StarFilled : Star"
            @click="handleToggleStar(currentArticle)"
          >{{ currentArticle.is_starred ? '取消收藏' : '收藏' }}</el-button>

          <el-button
            type="primary"
            :icon="MagicStick"
            @click="viewInAnalysis(currentArticle)"
          >在AI分析中查看</el-button>
        </div>
      </template>
    </el-drawer>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Search, Refresh, View, Download, Delete, Document, Link,
  Star, StarFilled, MagicStick,
} from '@element-plus/icons-vue'
import { articleApi, keywordApi } from '../api'

const router = useRouter()

// 关键词选项
const keywordOptions = ref([])

// 筛选条件
const filters = reactive({
  keyword_id: undefined,
  source_type: undefined,
  search: '',
  is_starred: false,
})

// 表格数据
const loading = ref(false)
const tableData = ref([])

// 分页
const pagination = reactive({
  page: 1,
  page_size: 20,
  total: 0,
})

// 详情抽屉
const drawerVisible = ref(false)
const detailLoading = ref(false)
const currentArticle = ref(null)

// 下载中的文章 id
const downloadingId = ref(null)

// 类型映射
const typeMap = {
  policy: { text: '政策', tag: 'warning' },
  news: { text: '资讯', tag: 'primary' },
  document: { text: '文档', tag: 'success' },
  pdf: { text: 'PDF', tag: 'danger' },
}

const typeText = (type) => typeMap[type]?.text || type || '未知'
const typeTagType = (type) => typeMap[type]?.tag || 'info'
const isPdf = (row) => row && (row.source_type === 'pdf' || row.file_type === 'pdf')
const isMobile = ref(window.innerWidth <= 760)
const updateMobileState = () => { isMobile.value = window.innerWidth <= 760 }

// 时间格式化
const formatDateTime = (val) => {
  if (!val) return '-'
  const d = new Date(val)
  if (isNaN(d.getTime())) return val
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 获取关键词列表
const fetchKeywords = async () => {
  try {
    const res = await keywordApi.list()
    keywordOptions.value = res.data || []
  } catch (e) {
    ElMessage.error('获取关键词列表失败')
  }
}

// 构建查询参数
const buildParams = () => {
  const params = {
    page: pagination.page,
    page_size: pagination.page_size,
  }
  if (filters.keyword_id) params.keyword_id = filters.keyword_id
  if (filters.source_type) params.source_type = filters.source_type
  if (filters.search.trim()) params.search = filters.search.trim()
  if (filters.is_starred) params.is_starred = true
  return params
}

// 获取文章列表
const fetchList = async () => {
  loading.value = true
  try {
    const res = await articleApi.list(buildParams())
    tableData.value = res.data.items || []
    pagination.total = res.data.total || 0
  } catch (e) {
    ElMessage.error('获取文章列表失败')
    tableData.value = []
    pagination.total = 0
  } finally {
    loading.value = false
  }
}

// 获取文章详情
const fetchDetail = async (id) => {
  detailLoading.value = true
  try {
    const res = await articleApi.get(id)
    currentArticle.value = res.data
  } catch (e) {
    ElMessage.error('获取文章详情失败')
    currentArticle.value = null
  } finally {
    detailLoading.value = false
  }
}

// 查询
const handleSearch = () => {
  pagination.page = 1
  fetchList()
}

// 重置
const handleReset = () => {
  filters.keyword_id = undefined
  filters.source_type = undefined
  filters.search = ''
  filters.is_starred = false
  pagination.page = 1
  fetchList()
}

// 分页变化
const handlePageChange = (page) => {
  pagination.page = page
  fetchList()
}

const handleSizeChange = (size) => {
  pagination.page_size = size
  pagination.page = 1
  fetchList()
}

// 行点击打开详情
const handleRowClick = (row) => {
  openDetail(row)
}

// 打开详情抽屉
const openDetail = (row) => {
  drawerVisible.value = true
  fetchDetail(row.id)
}

// 切换收藏
const handleToggleStar = async (row) => {
  try {
    const res = await articleApi.toggleStar(row.id)
    row.is_starred = res.data.is_starred
    // 同步更新详情中的文章
    if (currentArticle.value && currentArticle.value.id === row.id) {
      currentArticle.value.is_starred = res.data.is_starred
    }
    ElMessage.success(res.data.is_starred ? '已收藏' : '已取消收藏')
  } catch (e) {
    ElMessage.error('收藏操作失败')
  }
}

// 删除文章
const handleDelete = (row) => {
  ElMessageBox.confirm(
    `确定要删除文章《${row.title}》吗？删除后不可恢复。`,
    '删除确认',
    {
      confirmButtonText: '确定删除',
      cancelButtonText: '取消',
      type: 'warning',
    }
  )
    .then(async () => {
      try {
        await articleApi.delete(row.id)
        ElMessage.success('删除成功')
        // 若当前页删空且非首页，回退一页
        if (tableData.value.length === 1 && pagination.page > 1) {
          pagination.page--
        }
        fetchList()
      } catch (e) {
        ElMessage.error('删除失败')
      }
    })
    .catch(() => {})
}

// 下载 PDF
const handleDownload = async (row) => {
  downloadingId.value = row.id
  try {
    const res = await articleApi.download(row.id)
    const blob = new Blob([res.data], { type: 'application/pdf' })
    const url = window.URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    const safeTitle = (row.title || 'article').slice(0, 50).replace(/[\\/:*?"<>|]/g, '_')
    link.download = `${safeTitle}.pdf`
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
    window.URL.revokeObjectURL(url)
    ElMessage.success('下载成功')
  } catch (e) {
    ElMessage.error('下载失败，文件可能不存在')
  } finally {
    downloadingId.value = null
  }
}

// 在 AI 分析中查看
const viewInAnalysis = (row) => {
  drawerVisible.value = false
  router.push({ path: '/analysis', query: { article_id: row.id } })
}

// 初始化
onMounted(() => {
  window.addEventListener('resize', updateMobileState)
  fetchKeywords()
  fetchList()
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateMobileState)
})
</script>

<style scoped>
.collected-info {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 筛选栏 */
.filter-card {
  border-radius: 8px;
}

.filter-card :deep(.el-card__body) {
  padding: 18px 20px;
}

.filter-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px 24px;
}

.filter-item {
  display: flex;
  align-items: center;
  gap: 8px;
}

.filter-search {
  flex: 1;
  min-width: 240px;
}

.filter-label {
  font-size: 13px;
  color: #666;
  white-space: nowrap;
  font-weight: 500;
}

.filter-actions {
  margin-left: auto;
}

/* 表格卡片 */
.table-card {
  border-radius: 8px;
}

.table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.table-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 15px;
  font-weight: 600;
  color: #1d1e1f;
}

.table-total {
  font-size: 13px;
  color: #888;
}

/* 标题链接 */
.title-link {
  font-weight: 500;
  text-align: left;
  white-space: normal;
  line-height: 1.4;
}

.title-link :deep(.el-icon) {
  margin-right: 2px;
}

.star-icon {
  color: #e6a23c;
}

.text-muted {
  color: #bbb;
}

/* 分页 */
.pagination-wrap {
  display: flex;
  justify-content: flex-end;
  margin-top: 16px;
}

/* 详情抽屉 */
.detail-content {
  padding: 0 4px;
}

.detail-title {
  font-size: 20px;
  font-weight: 600;
  color: #1d1e1f;
  line-height: 1.5;
  margin-bottom: 20px;
}

.detail-meta {
  background: #f7f9fc;
  border-radius: 8px;
  padding: 16px 18px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.meta-row {
  display: flex;
  align-items: center;
  font-size: 14px;
  color: #444;
}

.meta-label {
  color: #888;
  width: 80px;
  flex-shrink: 0;
}

.link-icon {
  margin-left: 4px;
  font-size: 12px;
}

.attachment-list {
  display: grid;
  gap: 10px;
}

.attachment-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid #ebeef5;
  border-radius: 6px;
  background: #fafafa;
}

.attachment-item .el-link {
  min-width: 0;
  gap: 6px;
}

.attachment-item .el-link span {
  overflow-wrap: anywhere;
}

.detail-body {
  background: #fff;
  border: 1px solid #ebeef5;
  border-radius: 8px;
  padding: 18px 20px;
  max-height: calc(100vh - 420px);
  overflow-y: auto;
}

.detail-body pre {
  white-space: pre-wrap;
  word-wrap: break-word;
  word-break: break-word;
  font-family: -apple-system, 'Segoe UI', 'Microsoft YaHei', sans-serif;
  font-size: 14px;
  line-height: 1.8;
  color: #333;
  margin: 0;
}

/* 抽屉底部按钮 */
.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
  padding: 10px 0;
}

/* 表格行可点击提示 */
:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-table__row:hover) td {
  background: #ecf5ff !important;
}

@media (max-width: 760px) {
  .filter-item,
  .filter-search,
  .filter-actions {
    width: 100%;
  }

  .filter-item :deep(.el-select),
  .filter-item :deep(.el-input) {
    width: 100% !important;
  }

  .filter-actions {
    margin-left: 0;
  }

  .detail-title {
    font-size: 17px;
  }

  .attachment-item {
    align-items: flex-start;
    flex-direction: column;
  }

  .drawer-footer {
    flex-wrap: wrap;
  }
}
</style>
