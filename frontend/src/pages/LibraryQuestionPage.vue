<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api, ApiError } from '../api/client'
import { idempotentApi } from '../api/idempotency'
import type { CrossSurveyOverview, CrossSurveyStatistics, LibraryQuestion, LibraryVersion, QuestionBank, QuestionEditInput, QuestionShare, QuestionUsage } from '../api/types'
import LibraryQuestionForm from '../components/LibraryQuestionForm.vue'
import { useAuthStore } from '../stores/auth'
import { aggregateMetric, canManageLibrary } from '../utils/libraryPresentation'

const route = useRoute()
const questionId = String(route.params.id)
const auth = useAuthStore()
const question = ref<LibraryQuestion | null>(null)
const versions = ref<LibraryVersion[]>([])
const shares = ref<QuestionShare[]>([])
const usages = ref<QuestionUsage[]>([])
const banks = ref<QuestionBank[]>([])
const selectedVersionId = ref('')
const editBaseId = ref('')
const selectedBankId = ref('')
const recipientUsername = ref('')
const statistics = ref<CrossSurveyStatistics | null>(null)
const statisticsError = ref('')
const overview = ref<CrossSurveyOverview | null>(null)
const overviewError = ref('')
const pending = ref(false)
const error = ref('')
const success = ref('')
const owned = computed(() => !!question.value && canManageLibrary(question.value.ownerId, auth.user?.id))
const selectedVersion = computed(() => versions.value.find((item) => item.id === selectedVersionId.value) || null)
const editBase = computed(() => versions.value.find((item) => item.id === editBaseId.value) || null)

async function refresh() {
  error.value = ''
  try {
    const [current, history] = await Promise.all([
      api<LibraryQuestion>(`/library/questions/${questionId}`),
      api<LibraryVersion[]>(`/library/questions/${questionId}/versions`),
    ])
    question.value = current
    versions.value = history
    if (!selectedVersionId.value || !history.some((item) => item.id === selectedVersionId.value)) selectedVersionId.value = current.currentVersionId
    if (canManageLibrary(current.ownerId, auth.user?.id)) {
      [shares.value, usages.value, banks.value] = await Promise.all([
        api<QuestionShare[]>(`/library/questions/${questionId}/shares`),
        api<QuestionUsage[]>(`/library/questions/${questionId}/usages`),
        api<QuestionBank[]>('/question-banks'),
      ])
    } else { shares.value = []; usages.value = []; banks.value = [] }
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取题目失败' }
}

async function createVersion(payload: QuestionEditInput) {
  if (!editBase.value || pending.value) return
  const parentVersionId = editBase.value.id
  pending.value = true; error.value = ''; success.value = ''
  try {
    const created = await idempotentApi<LibraryVersion>(`create-version:${questionId}`, `/library/questions/${questionId}/versions`, {
      ...payload, parentVersionId,
    })
    editBaseId.value = ''
    selectedVersionId.value = created.id
    statistics.value = null
    statisticsError.value = ''
    overview.value = null
    await refresh()
    success.value = `版本 ${created.versionNo} 已创建；既有问卷快照保持原版本`
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '创建版本失败' }
  finally { pending.value = false }
}

async function restore(version: LibraryVersion) {
  if (pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    const created = await idempotentApi<LibraryVersion>(`restore:${questionId}:${version.id}`, `/library/questions/${questionId}/versions/${version.id}/restore`)
    selectedVersionId.value = created.id
    statistics.value = null
    statisticsError.value = ''
    overview.value = null
    await refresh()
    success.value = `已从版本 ${version.versionNo} 创建版本 ${created.versionNo}`
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '恢复失败' }
  finally { pending.value = false }
}

async function addToBank() {
  if (!selectedBankId.value || !selectedVersion.value || pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/question-banks/${selectedBankId.value}/items`, { method: 'POST', body: JSON.stringify({
      libraryQuestionId: questionId, selectedVersionId: selectedVersion.value.id,
    }) })
    success.value = '已加入题库；条目固定选定版本，后续新版不会自动切换'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '加入题库失败' }
  finally { pending.value = false }
}

async function grantShare() {
  if (pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/library/questions/${questionId}/shares`, { method: 'POST', body: JSON.stringify({ recipientUsername: recipientUsername.value.trim() }) })
    recipientUsername.value = ''
    shares.value = await api<QuestionShare[]>(`/library/questions/${questionId}/shares`)
    success.value = '分享授权已保存；对方可选用已提交版本'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '分享失败' }
  finally { pending.value = false }
}

async function revokeShare(recipientUserId: string) {
  if (pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/library/questions/${questionId}/shares/${recipientUserId}`, { method: 'DELETE' })
    shares.value = await api<QuestionShare[]>(`/library/questions/${questionId}/shares`)
    success.value = '已撤销后续选题权限；现有问卷快照不会删除'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '撤销失败' }
  finally { pending.value = false }
}

async function loadStatistics() {
  if (!selectedVersion.value) return
  statistics.value = null; statisticsError.value = ''
  try {
    statistics.value = await api<CrossSurveyStatistics>(`/library/questions/${questionId}/versions/${selectedVersion.value.id}/all-survey-statistics`)
  } catch (reason) {
    statisticsError.value = reason instanceof ApiError && reason.status === 409
      ? '统计期间有提交或范围变化，请刷新统计后重试'
      : reason instanceof Error ? reason.message : '统计读取失败'
  }
}

async function loadOverview() {
  overview.value = null; overviewError.value = ''
  try {
    overview.value = await api<CrossSurveyOverview>(`/library/questions/${questionId}/all-survey-statistics`)
  } catch (reason) {
    overviewError.value = reason instanceof ApiError && reason.status === 409
      ? '统计期间有提交或题目范围变化，请刷新后重试'
      : reason instanceof Error ? reason.message : '读取题目总览失败'
  }
}

function versionNo(id: string): string {
  return String(versions.value.find((item) => item.id === id)?.versionNo ?? '?')
}

function optionLabel(id: string): string {
  return selectedVersion.value?.options.find((item) => item.id === id)?.label || id
}

function groupOptionLabel(versionIds: string[], optionId: string): string {
  const version = versions.value.find((item) => item.id === versionIds[0])
  return version?.options.find((item) => item.id === optionId)?.label || optionId
}

function numericRangeLabel(bin: NonNullable<CrossSurveyStatistics['numericDistribution']>[number]): string {
  if (bin.lowerBound === bin.upperBound) return `等于 ${bin.lowerBound}`
  return `${bin.lowerBound} ≤ 数值 ${bin.upperInclusive ? '≤' : '<'} ${bin.upperBound}`
}

function numericBarWidth(count: number, bins: NonNullable<CrossSurveyStatistics['numericDistribution']>): string {
  const largest = Math.max(1, ...bins.map((bin) => bin.count))
  return `${count / largest * 100}%`
}

function validationLabel(version: LibraryVersion): string {
  const rules = version.validation
  const parts = [
    rules.minSelections === undefined ? '' : `最少选择 ${rules.minSelections}`,
    rules.maxSelections === undefined ? '' : `最多选择 ${rules.maxSelections}`,
    rules.minLength === undefined ? '' : `最少 ${rules.minLength} 字`,
    rules.maxLength === undefined ? '' : `最多 ${rules.maxLength} 字`,
    rules.minValue === undefined ? '' : `最小值 ${rules.minValue}`,
    rules.maxValue === undefined ? '' : `最大值 ${rules.maxValue}`,
    rules.integerOnly ? '仅整数' : '',
  ].filter(Boolean)
  return parts.length ? parts.join(' · ') : '无限制'
}

onMounted(async () => { await auth.loadUser(); await refresh() })
</script>

<template>
  <div class="page-container library-page">
    <RouterLink class="back-link" to="/library">← 返回个人题库</RouterLink>
    <section v-if="question" class="page-heading"><div><span class="eyebrow">QUESTION VERSIONS</span><h1>{{ question.currentVersion.title }}</h1><p>{{ owned ? '我的可复用题目' : '获分享的题目：可查看并选用已提交版本' }}</p></div><div class="heading-count"><strong>{{ versions.length }}</strong><span>个版本</span></div></section>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p v-if="success" class="form-success" role="status">{{ success }}</p>
    <template v-if="question">
      <section class="card library-panel"><h2>版本历史</h2><p class="notice">版本内容不可原位修改。恢复旧内容会创建新版本；已加入问卷的题目仍保留选用时的快照。</p>
        <div class="library-list"><article v-for="version in versions" :key="version.id" class="library-subcard"><div class="library-row"><strong>版本 {{ version.versionNo }} · {{ version.title }}</strong><span>{{ version.id === question.currentVersionId ? '当前版本' : '' }}</span></div><p>来源版本：{{ version.parentVersionId ? `版本 ${versionNo(version.parentVersionId)}` : '首版本' }} · {{ version.type }} · {{ version.required ? '必答' : '选答' }}</p><p v-if="version.options.length">选项：{{ version.options.map((option) => option.label).join(' / ') }}</p><p>校验：{{ validationLabel(version) }}</p><div class="library-actions"><button type="button" @click="selectedVersionId = version.id; statistics = null; statisticsError = ''">查看/统计此版</button><button v-if="owned" type="button" @click="editBaseId = version.id">以此版创建新版</button><button v-if="owned" type="button" :disabled="pending" @click="restore(version)">恢复此版为新版</button></div></article></div>
      </section>
      <section v-if="owned && editBase" class="card library-panel"><h2>基于版本 {{ editBase.versionNo }} 创建新版</h2><LibraryQuestionForm :key="editBase.id" :base-version="editBase" submit-label="保存为新版本" :pending="pending" @save="createVersion" /><button class="inline-button" type="button" @click="editBaseId = ''">取消</button></section>
      <section v-if="owned" class="card library-panel"><h2>加入个人题库</h2><p class="notice">选择下方查看中的版本加入题库；已有条目请到题库页面显式切换版本。</p><form class="form-stack" @submit.prevent="addToBank"><label>目标题库<select v-model="selectedBankId" required><option value="" disabled>请选择题库</option><option v-for="bank in banks" :key="bank.id" :value="bank.id">{{ bank.name }}</option></select></label><button class="button button-outline" :disabled="pending || !selectedVersion" type="submit">加入版本 {{ selectedVersion?.versionNo }}</button></form></section>
      <section v-if="owned" class="card library-panel"><h2>分享管理</h2><p class="notice">按接收者用户名授权；接收者可以选用已提交版本，不能修改版本或管理你的题库。</p><form class="form-stack" @submit.prevent="grantShare"><label>接收者用户名<input v-model="recipientUsername" required minlength="3" maxlength="40" /></label><button class="button button-outline" :disabled="pending" type="submit">授权分享</button></form><p v-if="!shares.length" class="notice">暂无有效分享。</p><div v-for="share in shares" :key="share.recipientUserId" class="library-row"><span>{{ share.recipientUsername || '已注销用户' }} <small>({{ share.recipientUserId }})</small></span><button type="button" :disabled="pending" @click="revokeShare(share.recipientUserId)">撤销</button></div></section>
      <section v-if="owned" class="card library-panel"><h2>版本使用情况</h2><p class="notice">按问卷ID区分使用记录，不显示他人问卷设置和答卷。</p><p v-if="!usages.length">暂无有效来源快照。</p><div v-for="usage in usages" :key="usage.questionId" class="library-row"><span>版本 {{ versionNo(usage.versionId) }} · {{ usage.status === 'draft' ? '草稿' : usage.status === 'published' ? '已发布' : '已关闭' }} · {{ usage.isOwnSurvey ? '我的问卷' : '他人问卷' }}<small>问卷ID：{{ usage.surveyId }} · 实例ID：{{ usage.questionId }}</small></span><RouterLink v-if="usage.isOwnSurvey" :to="`/surveys/${usage.surveyId}/edit`">查看问卷</RouterLink></div></section>
      <section v-if="owned" class="card library-panel"><h2>逻辑题目跨问卷总览</h2><p class="notice">自动纳入所有使用有效来源快照的问卷。内容完全相同的版本合并展示；内容不同的版本分开展示。只返回汇总，不显示填写者身份。</p><button class="button button-outline" type="button" @click="loadOverview">刷新总览</button><p v-if="overviewError" class="form-error" role="alert">{{ overviewError }}</p><div v-for="group in overview?.groups || []" :key="group.versionIds.join('-')" class="library-subcard"><h3>版本 {{ group.versionNumbers.join('、') }}</h3><p>参与问卷 {{ group.statistics.participatingSurveyCount }} 份</p><p v-if="group.statistics.suppression.applied" role="status">样本不足，答卷层面结果已隐藏。</p><template v-else><p>答卷 {{ group.statistics.responseCount }} 份 · 到达 {{ group.statistics.reachedCount }} 份 · 回答 {{ group.statistics.answeredCount }} 份</p><p v-if="group.statistics.average !== undefined">数字平均值：{{ group.statistics.average ?? '暂无' }}</p><ul v-if="group.statistics.optionCounts"><li v-for="item in group.statistics.optionCounts" :key="item.optionId">{{ groupOptionLabel(group.versionIds, item.optionId) }}：{{ item.count }}</li></ul><ul v-if="group.statistics.textAnswerCounts"><li v-for="item in group.statistics.textAnswerCounts" :key="item.value">{{ item.value }}：{{ item.count }}份</li></ul><div v-if="group.statistics.numericDistribution?.length" class="numeric-distribution"><h3>数值分布</h3><div v-for="(bin, index) in group.statistics.numericDistribution" :key="index" class="numeric-bin"><span>{{ numericRangeLabel(bin) }}</span><div class="numeric-bin-track"><div class="numeric-bin-bar" :style="{ width: numericBarWidth(bin.count, group.statistics.numericDistribution) }"></div></div><strong>{{ bin.count }}份</strong></div></div></template></div></section>
      <section v-if="owned && selectedVersion" class="card library-panel"><h2>版本 {{ selectedVersion.versionNo }} 的跨问卷统计</h2><p class="notice">自动汇总所有使用该版本的问卷；参与问卷数可包含草稿。数字题每份答卷等权计数，文本只显示至少5名不同填写者给出的重复答案。</p><button class="button button-outline" type="button" @click="loadStatistics">刷新统计</button><p v-if="statisticsError" class="form-error" role="alert">{{ statisticsError }}</p><div v-if="statistics" class="library-stats"><p>参与问卷 {{ statistics.participatingSurveyCount }} 份 · 范围：所有使用此版本的问卷</p><p v-if="statistics.suppression.applied" role="status">样本不足（任一非零统计少于 {{ statistics.suppression.minimumDistinctRespondents }} 名不同填写者），答卷计数、均值和分布已抑制。</p><template v-else><p>答卷 {{ aggregateMetric(statistics.responseCount, false) }} 份 · 到达 {{ aggregateMetric(statistics.reachedCount, false) }} 份 · 回答 {{ aggregateMetric(statistics.answeredCount, false) }} 份</p><p v-if="statistics.average !== undefined">数字平均值：{{ statistics.average === null ? '暂无' : statistics.average }}</p><div v-if="statistics.numericDistribution?.length" class="numeric-distribution"><h3>数值分布（按答卷计）</h3><p class="notice">区间根据当前回答值划分；新增答卷后边界可能变化。</p><div v-for="(bin, index) in statistics.numericDistribution" :key="index" class="numeric-bin"><span>{{ numericRangeLabel(bin) }}</span><div class="numeric-bin-track"><div class="numeric-bin-bar" :style="{ width: numericBarWidth(bin.count, statistics.numericDistribution) }"></div></div><strong>{{ bin.count }}份</strong></div></div><ul v-if="statistics.optionCounts"><li v-for="option in statistics.optionCounts" :key="option.optionId">{{ optionLabel(option.optionId) }}：{{ option.count }}</li></ul><ul v-if="statistics.textAnswerCounts"><li v-for="item in statistics.textAnswerCounts" :key="item.value">{{ item.value }}：{{ item.count }}份</li></ul></template></div></section>
    </template>
  </div>
</template>
