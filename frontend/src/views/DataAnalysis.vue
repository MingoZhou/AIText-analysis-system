<template>
  <div class="data-analysis-page" v-loading="loading">
    <!-- ========== 顶部控制栏 ========== -->
    <el-card shadow="never" class="control-card">
      <div class="control-bar">
        <div class="control-item">
          <span class="control-label">关键词</span>
          <el-select
            v-model="selectedKeywordId"
            placeholder="按关键词筛选"
            clearable
            filterable
            style="width: 220px"
            @change="onKeywordChange"
          >
            <el-option
              v-for="kw in keywords"
              :key="kw.id"
              :label="kw.keyword"
              :value="kw.id"
            />
          </el-select>
        </div>

        <div class="control-divider">或</div>

        <div class="control-item">
          <span class="control-label">文章</span>
          <el-select
            v-model="selectedArticleIds"
            multiple
            collapse-tags
            collapse-tags-tooltip
            placeholder="可多选文章"
            filterable
            style="width: 320px"
            :disabled="!!selectedKeywordId"
          >
            <el-option
              v-for="art in articles"
              :key="art.id"
              :label="art.title"
              :value="art.id"
            />
          </el-select>
        </div>

        <div class="control-actions">
          <el-button type="primary" :loading="loading" @click="generateAnalysis">
            <el-icon class="btn-icon"><DataLine /></el-icon>
            生成分析
          </el-button>
          <el-button :loading="loading" @click="refresh">
            <el-icon class="btn-icon"><Refresh /></el-icon>
            刷新
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- ========== 汇总统计 ========== -->
    <el-row v-if="hasResult" :gutter="16" class="stat-row">
      <el-col :xs="24" :sm="12" :md="8">
        <el-card shadow="hover" class="stat-card" :body-style="{ padding: '18px 20px' }">
          <div class="stat-inner">
            <el-icon class="stat-icon" style="background-color: #409eff">
              <Document />
            </el-icon>
            <div class="stat-info">
              <div class="stat-value" style="color: #409eff">{{ totalArticles }}</div>
              <div class="stat-label">分析文章数</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8">
        <el-card shadow="hover" class="stat-card" :body-style="{ padding: '18px 20px' }">
          <div class="stat-inner">
            <el-icon class="stat-icon" style="background-color: #67c23a">
              <Cloudy />
            </el-icon>
            <div class="stat-info">
              <div class="stat-value" style="color: #67c23a">{{ wordCount }}</div>
              <div class="stat-label">词条数量</div>
            </div>
          </div>
        </el-card>
      </el-col>
      <el-col :xs="24" :sm="12" :md="8">
        <el-card shadow="hover" class="stat-card" :body-style="{ padding: '18px 20px' }">
          <div class="stat-inner">
            <el-icon class="stat-icon" style="background-color: #9254de">
              <TrendCharts />
            </el-icon>
            <div class="stat-info">
              <div class="stat-value" style="color: #9254de">{{ chartCount }}</div>
              <div class="stat-label">可视化图表</div>
            </div>
          </div>
        </el-card>
      </el-col>
    </el-row>

    <!-- ========== 结果区域 ========== -->
    <template v-if="hasResult">
      <!-- 词云 -->
      <el-card shadow="hover" class="section-card">
        <div ref="wordcloudChart" class="chart-box wc-box"></div>
        <div class="chart-title">词云分析</div>
      </el-card>

      <!-- 图表网格 -->
      <el-row :gutter="16" class="chart-grid">
        <el-col :xs="24" :md="12">
          <el-card shadow="hover" class="section-card">
            <div ref="sourceChart" class="chart-box"></div>
            <div class="chart-title">来源分布</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="hover" class="section-card">
            <div ref="topicChart" class="chart-box"></div>
            <div class="chart-title">主题分布</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="hover" class="section-card">
            <div ref="keywordFreqChart" class="chart-box"></div>
            <div class="chart-title">关键词频次</div>
          </el-card>
        </el-col>
        <el-col :xs="24" :md="12">
          <el-card shadow="hover" class="section-card">
            <div ref="keywordDistChart" class="chart-box"></div>
            <div class="chart-title">关键词分布</div>
          </el-card>
        </el-col>
        <el-col :span="24">
          <el-card shadow="hover" class="section-card">
            <div ref="timeTrendChart" class="chart-box"></div>
            <div class="chart-title">时间趋势</div>
          </el-card>
        </el-col>
      </el-row>
    </template>

    <!-- ========== 空状态 ========== -->
    <el-card v-else shadow="never" class="empty-card">
      <el-empty description="选择关键词或文章后，点击「生成分析」查看数据可视化结果" />
    </el-card>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { ElMessage } from 'element-plus'
import {
  Refresh, DataLine, Document, Cloudy, TrendCharts,
} from '@element-plus/icons-vue'
import * as echarts from 'echarts'
import 'echarts-wordcloud'
import { analysisApi, keywordApi, articleApi } from '../api'

const CHART_COLORS = ['#409eff', '#67c23a', '#e6a23c', '#f56c6c', '#909399', '#9254de', '#36cfc9']

// ========== 状态 ==========
const loading = ref(false)
const keywords = ref([])
const articles = ref([])
const selectedKeywordId = ref(null)
const selectedArticleIds = ref([])

const hasResult = ref(false)
const totalArticles = ref(0)
const wordCount = ref(0)
const chartCount = ref(0)

// ========== 图表 DOM 引用 ==========
const wordcloudChart = ref(null)
const sourceChart = ref(null)
const topicChart = ref(null)
const keywordFreqChart = ref(null)
const timeTrendChart = ref(null)
const keywordDistChart = ref(null)

// ========== 图表实例 ==========
let wcInstance = null
let sourceInstance = null
let topicInstance = null
let kwFreqInstance = null
let timeTrendInstance = null
let kwDistInstance = null

// ========== 数据加载 ==========
async function loadKeywords() {
  try {
    const res = await keywordApi.list()
    keywords.value = res.data || []
  } catch (e) {
    ElMessage.error('加载关键词失败')
  }
}

async function loadArticles() {
  try {
    const res = await articleApi.list({ page: 1, page_size: 100 })
    articles.value = res.data.items || []
  } catch (e) {
    articles.value = []
  }
}

async function onKeywordChange() {
  selectedArticleIds.value = []
  if (selectedKeywordId.value) {
    try {
      const res = await articleApi.list({
        keyword_id: selectedKeywordId.value,
        page: 1,
        page_size: 100,
      })
      articles.value = res.data.items || []
    } catch (e) {
      articles.value = []
    }
  } else {
    await loadArticles()
  }
}

// ========== 生成分析 ==========
async function generateAnalysis() {
  const hasSelection = selectedKeywordId.value || selectedArticleIds.value.length > 0
  if (!hasSelection) {
    ElMessage.warning('请先选择关键词或文章')
    return
  }

  loading.value = true
  const payload = {
    keyword_id: selectedKeywordId.value || null,
    article_ids: selectedArticleIds.value,
  }

  try {
    const [wcRes, chartRes] = await Promise.all([
      analysisApi.wordcloud(payload),
      analysisApi.chart(payload),
    ])

    const wcData = wcRes.data || {}
    const chartData = chartRes.data || {}

    if (wcData.error) {
      ElMessage.error(wcData.error)
      loading.value = false
      return
    }
    if (chartData.error) {
      ElMessage.error(chartData.error)
      loading.value = false
      return
    }

    hasResult.value = true
    totalArticles.value = wcData.total_articles || chartData.total_articles || 0
    wordCount.value = (wcData.words || []).length

    const charts = chartData.charts || {}
    let count = 0
    if (charts.source_distribution) count++
    if (charts.topic_distribution) count++
    if (charts.keyword_frequency) count++
    if (charts.time_trend) count++
    if (charts.keyword_distribution) count++
    chartCount.value = count

    await nextTick()
    if (wcData.words && wcData.words.length) {
      renderWordcloud(wcData.words)
    }
    renderAllCharts(charts)

    ElMessage.success('分析完成')
  } catch (e) {
    ElMessage.error('分析请求失败')
  } finally {
    loading.value = false
  }
}

// ========== 词云渲染 ==========
function renderWordcloud(words) {
  if (wcInstance) wcInstance.dispose()
  wcInstance = echarts.init(wordcloudChart.value)
  wcInstance.setOption({
    tooltip: { show: true },
    series: [{
      type: 'wordCloud',
      shape: 'circle',
      sizeRange: [14, 60],
      rotationRange: [-45, 45],
      gridSize: 8,
      textStyle: {
        fontFamily: 'Microsoft YaHei',
        color: () => `rgb(${Math.random() * 100 + 50}, ${Math.random() * 100 + 80}, ${Math.random() * 155 + 100})`,
      },
      data: words.map(w => ({ name: w.name, value: w.value })),
    }],
  })
}

// ========== 图表渲染 ==========
function renderAllCharts(charts) {
  if (sourceChart.value && charts.source_distribution) {
    if (sourceInstance) sourceInstance.dispose()
    sourceInstance = echarts.init(sourceChart.value)
    sourceInstance.setOption(makePieOption('来源分布', charts.source_distribution))
  }
  if (topicChart.value && charts.topic_distribution) {
    if (topicInstance) topicInstance.dispose()
    topicInstance = echarts.init(topicChart.value)
    topicInstance.setOption(makePieOption('主题分布', charts.topic_distribution))
  }
  if (keywordFreqChart.value && charts.keyword_frequency) {
    if (kwFreqInstance) kwFreqInstance.dispose()
    kwFreqInstance = echarts.init(keywordFreqChart.value)
    kwFreqInstance.setOption(makeBarOption('关键词频次', charts.keyword_frequency))
  }
  if (timeTrendChart.value && charts.time_trend) {
    if (timeTrendInstance) timeTrendInstance.dispose()
    timeTrendInstance = echarts.init(timeTrendChart.value)
    timeTrendInstance.setOption(makeLineOption('时间趋势', charts.time_trend))
  }
  if (keywordDistChart.value && charts.keyword_distribution) {
    if (kwDistInstance) kwDistInstance.dispose()
    kwDistInstance = echarts.init(keywordDistChart.value)
    kwDistInstance.setOption(makeHorizontalBarOption('关键词分布', charts.keyword_distribution))
  }
}

// 兼容多种字段名的数据归一化
function normalize(arr) {
  if (!Array.isArray(arr)) return []
  return arr.map(d => ({
    name: d.name || d.label || d.type || d.keyword || d.source || d.date || d.day || d.time || '未知',
    value: Number(d.value ?? d.count ?? d.num ?? 0),
  }))
}

function makePieOption(title, data) {
  const d = normalize(data)
  return {
    title: { text: title, left: 'center', top: 8, textStyle: { fontSize: 14, color: '#1d1e1f' } },
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    legend: { bottom: '2%', left: 'center', textStyle: { color: '#666' } },
    color: CHART_COLORS,
    series: [{
      type: 'pie',
      radius: ['40%', '65%'],
      center: ['50%', '46%'],
      avoidLabelOverlap: true,
      itemStyle: { borderColor: '#fff', borderWidth: 2 },
      label: { show: false },
      emphasis: { label: { show: true, fontSize: 14, fontWeight: 'bold' } },
      data: d.length ? d : [{ name: '暂无数据', value: 1 }],
    }],
  }
}

function makeBarOption(title, data) {
  const d = normalize(data)
  const names = d.map(x => x.name)
  const values = d.map(x => x.value)
  return {
    title: { text: title, left: 'center', top: 8, textStyle: { fontSize: 14, color: '#1d1e1f' } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '4%', bottom: '4%', top: '18%', containLabel: true },
    xAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#666', rotate: names.length > 6 ? 30 : 0, interval: 0 },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#666' },
    },
    series: [{
      type: 'bar',
      barMaxWidth: 36,
      data: values,
      itemStyle: {
        borderRadius: [4, 4, 0, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: '#409eff' },
          { offset: 1, color: '#79bbff' },
        ]),
      },
    }],
  }
}

function makeLineOption(title, data) {
  const d = normalize(data)
  const names = d.map(x => x.name)
  const values = d.map(x => x.value)
  return {
    title: { text: title, left: 'center', top: 8, textStyle: { fontSize: 14, color: '#1d1e1f' } },
    tooltip: { trigger: 'axis' },
    grid: { left: '3%', right: '4%', bottom: '4%', top: '18%', containLabel: true },
    xAxis: {
      type: 'category',
      data: names,
      boundaryGap: false,
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#666', hideOverlap: true },
    },
    yAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#666' },
    },
    series: [{
      type: 'line',
      smooth: true,
      symbol: 'circle',
      symbolSize: 7,
      data: values,
      itemStyle: { color: '#67c23a' },
      lineStyle: { width: 3, color: '#67c23a' },
      areaStyle: {
        color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(103,194,58,0.35)' },
          { offset: 1, color: 'rgba(103,194,58,0.02)' },
        ]),
      },
    }],
  }
}

function makeHorizontalBarOption(title, data) {
  const d = normalize(data)
  const sorted = [...d].sort((a, b) => a.value - b.value)
  const names = sorted.map(x => x.name)
  const values = sorted.map(x => x.value)
  return {
    title: { text: title, left: 'center', top: 8, textStyle: { fontSize: 14, color: '#1d1e1f' } },
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: '3%', right: '6%', bottom: '4%', top: '18%', containLabel: true },
    xAxis: {
      type: 'value',
      axisLine: { show: false },
      axisTick: { show: false },
      splitLine: { lineStyle: { color: '#f0f0f0' } },
      axisLabel: { color: '#666' },
    },
    yAxis: {
      type: 'category',
      data: names,
      axisLine: { lineStyle: { color: '#dcdfe6' } },
      axisLabel: { color: '#666' },
    },
    series: [{
      type: 'bar',
      barMaxWidth: 24,
      data: values,
      itemStyle: {
        borderRadius: [0, 4, 4, 0],
        color: new echarts.graphic.LinearGradient(0, 0, 1, 0, [
          { offset: 0, color: '#9254de' },
          { offset: 1, color: '#b37feb' },
        ]),
      },
    }],
  }
}

// ========== 刷新 / 重置 ==========
async function refresh() {
  selectedKeywordId.value = null
  selectedArticleIds.value = []
  hasResult.value = false
  totalArticles.value = 0
  wordCount.value = 0
  chartCount.value = 0
  disposeAll()
  await loadKeywords()
  await loadArticles()
  ElMessage.success('已刷新')
}

// ========== 缩放 / 销毁 ==========
function handleResize() {
  wcInstance && wcInstance.resize()
  sourceInstance && sourceInstance.resize()
  topicInstance && topicInstance.resize()
  kwFreqInstance && kwFreqInstance.resize()
  timeTrendInstance && timeTrendInstance.resize()
  kwDistInstance && kwDistInstance.resize()
}

function disposeAll() {
  if (wcInstance) { wcInstance.dispose(); wcInstance = null }
  if (sourceInstance) { sourceInstance.dispose(); sourceInstance = null }
  if (topicInstance) { topicInstance.dispose(); topicInstance = null }
  if (kwFreqInstance) { kwFreqInstance.dispose(); kwFreqInstance = null }
  if (timeTrendInstance) { timeTrendInstance.dispose(); timeTrendInstance = null }
  if (kwDistInstance) { kwDistInstance.dispose(); kwDistInstance = null }
}

// ========== 生命周期 ==========
onMounted(async () => {
  await loadKeywords()
  await loadArticles()
  window.addEventListener('resize', handleResize)
})

onBeforeUnmount(() => {
  window.removeEventListener('resize', handleResize)
  disposeAll()
})
</script>

<style scoped>
.data-analysis-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 控制栏 */
.control-card {
  border-radius: 8px;
}
.control-bar {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 16px;
}
.control-item {
  display: flex;
  align-items: center;
  gap: 8px;
}
.control-label {
  font-size: 14px;
  font-weight: 600;
  color: #1d1e1f;
  white-space: nowrap;
}
.control-divider {
  font-size: 13px;
  color: #bbb;
}
.control-actions {
  margin-left: auto;
  display: flex;
  gap: 8px;
}
.btn-icon {
  margin-right: 4px;
}

/* 统计卡片 */
.stat-row {
  margin-bottom: 0 !important;
}
.stat-card {
  border-radius: 8px;
  transition: transform 0.2s ease, box-shadow 0.2s ease;
}
.stat-card:hover {
  transform: translateY(-3px);
}
.stat-inner {
  display: flex;
  align-items: center;
  gap: 14px;
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
.stat-value {
  font-size: 26px;
  font-weight: 700;
  line-height: 1;
}
.stat-label {
  font-size: 13px;
  color: #999;
  margin-top: 6px;
}

/* 图表区 */
.section-card {
  border-radius: 8px;
  transition: box-shadow 0.2s ease;
}
.chart-box {
  width: 100%;
  min-height: 320px;
  height: 320px;
}
.wc-box {
  height: 360px;
}
.chart-title {
  text-align: center;
  font-size: 14px;
  font-weight: 600;
  color: #1d1e1f;
  margin-top: 12px;
  padding-top: 10px;
  border-top: 1px solid #f0f0f0;
}
.chart-grid {
  margin-bottom: 0 !important;
}
.chart-grid .el-col {
  margin-bottom: 16px;
}

/* 空状态 */
.empty-card {
  border-radius: 8px;
  min-height: 400px;
  display: flex;
  align-items: center;
  justify-content: center;
}

:deep(.el-card__body) {
  padding: 16px 20px;
}
</style>
