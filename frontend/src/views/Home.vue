<template>
  <div class="home-page">
    <!-- 顶部统计卡片 -->
    <el-row :gutter="16" class="stat-row">
      <el-col :xs="24" :sm="12" :md="8" :lg="6" :xl="4" v-for="(card, idx) in statCards" :key="idx">
        <el-card shadow="hover" class="stat-card" :body-style="{ padding: '18px 20px' }">
          <div class="stat-card-inner">
            <div class="stat-left">
              <el-icon class="stat-icon" :style="{ backgroundColor: card.color }">
                <component :is="card.icon" />
              </el-icon>
              <div class="stat-number" :style="{ color: card.color }">{{ card.value }}</div>
            </div>
            <div class="stat-right">
              <div class="stat-label">{{ card.label }}</div>
              <div class="stat-sub">{{ card.sub }}</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 图表区域 -->
    <el-row :gutter="16" class="chart-row">
      <el-col :xs="24" :md="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <el-icon><TrendCharts /></el-icon>
              <span>近7天采集趋势</span>
            </div>
          </template>
          <div ref="trendChartRef" class="chart-box"></div>
        </el-card>
      </el-col>
      <el-col :xs="24" :md="12">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <el-icon><PieChart /></el-icon>
              <span>文章类型分布</span>
            </div>
          </template>
          <div ref="typeChartRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <el-row :gutter="16" class="chart-row">
      <el-col :span="24">
        <el-card shadow="hover" class="chart-card">
          <template #header>
            <div class="card-header">
              <el-icon><DataLine /></el-icon>
              <span>关键词分布</span>
            </div>
          </template>
          <div ref="keywordChartRef" class="chart-box"></div>
        </el-card>
      </el-col>
    </el-row>

    <!-- 最近采集文章列表 -->
    <el-card shadow="hover" class="recent-card">
      <template #header>
        <div class="card-header">
          <el-icon><Document /></el-icon>
          <span>最近采集文章</span>
          <el-button type="primary" link class="more-btn" @click="goArticles">
            查看全部
            <el-icon class="el-icon--right"><ArrowRight /></el-icon>
          </el-button>
        </div>
      </template>
      <el-table
        :data="recentArticles"
        stripe
        highlight-current-row
        style="width: 100%"
        :header-cell-style="{ background: '#fafafa', color: '#333' }"
        @row-click="goArticles"
        empty-text="暂无采集记录"
      >
        <el-table-column type="index" label="#" width="60" />
        <el-table-column prop="title" label="标题" min-width="240" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="article-title">{{ row.title }}</span>
          </template>
        </el-table-column>
        <el-table-column label="关键词" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag
              v-for="(kw, i) in formatKeywords(row.keyword_texts?.length ? row.keyword_texts : row.keyword_text)"
              :key="i"
              size="small"
              class="kw-tag"
              effect="plain"
            >
              {{ kw }}
            </el-tag>
            <span v-if="!formatKeywords(row.keyword_texts?.length ? row.keyword_texts : row.keyword_text).length" class="text-muted">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="source" label="来源" width="140" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.source_name || '-' }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="type" label="类型" width="110">
          <template #default="{ row }">
            <el-tag :type="typeTagType(row.source_type)" size="small">
              {{ typeText(row.source_type) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="collected_at" label="采集时间" width="180">
          <template #default="{ row }">
            <span>{{ formatTime(row.crawl_date) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import * as echarts from 'echarts'
import { ElMessage } from 'element-plus'
import {
  Key, Document, Collection, StarFilled, Files, Cpu,
  TrendCharts, PieChart, DataLine, ArrowRight,
} from '@element-plus/icons-vue'
import { dashboardApi } from '../api'

const router = useRouter()

// 图表 DOM 引用
const trendChartRef = ref(null)
const typeChartRef = ref(null)
const keywordChartRef = ref(null)

// 图表实例
let trendChart = null
let typeChart = null
let keywordChart = null

// 统计数据
const stats = reactive({
  keyword_count: 0,
  article_count: 0,
  unread_count: 0,
  star_count: 0,
  pdf_count: 0,
  provider_count: 0,
})

const trendData = ref([])
const typeDistribution = ref([])
const keywordDistribution = ref([])
const recentArticles = ref([])

// 统计卡片
const statCards = computed(() => [
  { label: '关键词数', sub: '监控关键词', value: stats.keyword_count, color: '#409eff', icon: Key },
  { label: '文章总数', sub: '已采集文章', value: stats.article_count, color: '#67c23a', icon: Document },
  { label: '未读数', sub: '待阅读文章', value: stats.unread_count, color: '#e6a23c', icon: Collection },
  { label: '收藏数', sub: '已收藏文章', value: stats.star_count, color: '#f56c6c', icon: StarFilled },
  { label: 'PDF文件数', sub: 'PDF 资源', value: stats.pdf_count, color: '#909399', icon: Files },
  { label: 'AI提供商数', sub: '已配置', value: stats.provider_count, color: '#9c27b0', icon: Cpu },
])

// 跳转文章列表
const goArticles = () => {
  router.push('/articles')
}

// 关键词格式化
const formatKeywords = (kws) => {
  if (!kws) return []
  if (Array.isArray(kws)) return kws
  if (typeof kws === 'string') {
    try {
      const parsed = JSON.parse(kws)
      if (Array.isArray(parsed)) return parsed
    } catch (e) {
      // 非合法 JSON，按分隔符拆分
    }
    return kws.split(/[,，、;；\s]+/).filter(Boolean)
  }
  return []
}

// 时间格式化
const formatTime = (t) => {
  if (!t) return '-'
  const d = new Date(t)
  if (isNaN(d.getTime())) return String(t)
  const pad = (n) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
}

// 类型标签颜色
const typeTagType = (type) => {
  const map = {
    通用: '', 政策: 'warning', 技术: 'success', 市场: 'danger',
    general: '', policy: 'warning', tech: 'success', market: 'danger',
    document: 'success', news: 'primary', pdf: 'danger',
  }
  return map[type] || 'info'
}

const typeText = (type) => ({
  policy: '政策', news: '资讯', document: '文档', pdf: 'PDF',
}[type] || type || '未分类')

// 安全取数
const num = (v) => {
  const n = Number(v)
  return isNaN(n) ? 0 : n
}

// 初始化趋势折线图
const initTrendChart = () => {
  if (!trendChartRef.value) return
  trendChart = echarts.init(trendChartRef.value)
  const data = trendData.value || []
  const dates = data.map((d) => d.date || d.day || d.time || '')
  const counts = data.map((d) => num(d.count ?? d.value ?? d.articles ?? d.num))
  trendChart.setOption({
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '3%', top: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: dates,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: {
        color: '#666',
        hideOverlap: true,
        formatter: (value) => value.length >= 10 ? value.slice(5) : value,
      },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#666' },
    },
    series: [
      {
        name: '采集数',
        type: 'line',
        smooth: true,
        symbol: 'circle',
        symbolSize: 7,
        data: counts,
        itemStyle: { color: '#409eff' },
        lineStyle: { width: 3, color: '#409eff' },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: 'rgba(64,158,255,0.35)' },
            { offset: 1, color: 'rgba(64,158,255,0.02)' },
          ]),
        },
      },
    ],
  })
}

// 初始化类型饼图
const initTypeChart = () => {
  if (!typeChartRef.value) return
  typeChart = echarts.init(typeChartRef.value)
  const data = (typeDistribution.value || []).map((d) => ({
    name: d.name || d.type || d.label || '未知',
    value: num(d.value ?? d.count ?? d.num),
  }))
  typeChart.setOption({
    tooltip: { trigger: 'item', formatter: '{a} <br/>{b}: {c} ({d}%)' },
    legend: {
      bottom: '2%',
      left: 'center',
      textStyle: { color: '#666' },
    },
    color: ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#9c27b0', '#909399', '#00b4d8', '#ff7f50'],
    series: [
      {
        name: '文章类型',
        type: 'pie',
        radius: ['42%', '68%'],
        center: ['50%', '45%'],
        avoidLabelOverlap: true,
        itemStyle: { borderColor: '#fff', borderWidth: 2 },
        label: { show: false },
        emphasis: {
          label: { show: true, fontSize: 14, fontWeight: 'bold' },
        },
        data: data.length ? data : [{ name: '暂无数据', value: 1 }],
      },
    ],
  })
}

// 初始化关键词柱状图
const initKeywordChart = () => {
  if (!keywordChartRef.value) return
  keywordChart = echarts.init(keywordChartRef.value)
  const data = (keywordDistribution.value || []).map((d) => ({
    name: d.keyword || d.name || d.label || '未知',
    value: num(d.count ?? d.value ?? d.num),
  }))
  const names = data.map((d) => d.name)
  const values = data.map((d) => d.value)
  keywordChart.setOption({
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '8%', top: '12%', containLabel: true },
    xAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#666', rotate: names.length > 8 ? 30 : 0, interval: 0 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#666' },
    },
    series: [
      {
        name: '文章数',
        type: 'bar',
        barMaxWidth: 40,
        data: values,
        itemStyle: {
          borderRadius: [4, 4, 0, 0],
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: '#409eff' },
            { offset: 1, color: '#79bbff' },
          ]),
        },
      },
    ],
  })
}

// 窗口缩放自适应
const handleResize = () => {
  trendChart && trendChart.resize()
  typeChart && typeChart.resize()
  keywordChart && keywordChart.resize()
}

// 加载数据
const loadData = async () => {
  try {
    const { data } = await dashboardApi.getStats()
    const res = data || {}
    // 兼容 stats 嵌套或扁平结构
    const s = res.stats || res
    stats.keyword_count = num(s.keyword_count ?? s.keywords)
    stats.article_count = num(s.article_count ?? s.articles)
    stats.unread_count = num(s.unread_count ?? s.unread)
    stats.star_count = num(s.star_count ?? s.starred_count ?? s.starred ?? s.stars)
    stats.pdf_count = num(s.pdf_count ?? s.pdfs)
    stats.provider_count = num(s.provider_count ?? s.providers)

    trendData.value = res.trend_data || res.trend || []
    // type_distribution 从 API 返回的是字典 {type: count}，需转为数组
    const td = res.type_distribution || res.types || {}
    const typeLabels = { policy: '政策', news: '资讯', document: '文档', pdf: 'PDF' }
    typeDistribution.value = Array.isArray(td)
      ? td
      : Object.entries(td).map(([k, v]) => ({ name: typeLabels[k] || k, value: v }))
    keywordDistribution.value = res.keyword_distribution || res.keywords_dist || []
    recentArticles.value = res.recent_articles || res.recent || []

    await nextTick()
    initTrendChart()
    initTypeChart()
    initKeywordChart()
  } catch (err) {
    console.error('加载看板数据失败', err)
    ElMessage.error('加载看板数据失败')
  }
}

onMounted(() => {
  loadData()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  trendChart && trendChart.dispose()
  typeChart && typeChart.dispose()
  keywordChart && keywordChart.dispose()
})
</script>

<style scoped>
.home-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.stat-row {
  margin-bottom: 0;
}

.stat-card {
  border-radius: 8px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stat-card:hover {
  transform: translateY(-3px);
}

.stat-card-inner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.stat-left {
  display: flex;
  align-items: center;
  gap: 12px;
  flex: 1;
  min-width: 0;
}

.stat-icon {
  width: 44px;
  height: 44px;
  border-radius: 10px;
  color: #fff;
  font-size: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.stat-number {
  font-size: 26px;
  font-weight: 700;
  line-height: 1;
  min-width: 0;
  word-break: break-all;
}

.stat-right {
  text-align: right;
  flex-shrink: 0;
}

.stat-label {
  font-size: 14px;
  color: #1d1e1f;
  font-weight: 600;
  white-space: nowrap;
}

.stat-sub {
  font-size: 12px;
  color: #999;
  margin-top: 4px;
  white-space: nowrap;
}

.chart-row {
  margin-bottom: 0 !important;
}

.chart-card {
  border-radius: 8px;
}

.card-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-weight: 600;
  color: #1d1e1f;
  font-size: 15px;
}

.more-btn {
  margin-left: auto;
}

.chart-box {
  width: 100%;
  height: 300px;
}

.recent-card {
  border-radius: 8px;
}

.article-title {
  color: #303133;
  font-weight: 500;
  cursor: pointer;
}
.article-title:hover {
  color: #409eff;
}

.kw-tag {
  margin: 0 4px 4px 0;
}

.text-muted {
  color: #c0c4cc;
}

:deep(.el-table__row) {
  cursor: pointer;
}

:deep(.el-card__header) {
  padding: 14px 20px;
  border-bottom: 1px solid #f0f0f0;
}
</style>
