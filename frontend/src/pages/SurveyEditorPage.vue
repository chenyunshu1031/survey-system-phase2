<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { RouterLink, useRoute } from 'vue-router'
import { api } from '../api/client'
import { idempotentApi } from '../api/idempotency'
import JumpRuleEditor from '../components/JumpRuleEditor.vue'
import LibraryPicker from '../components/LibraryPicker.vue'
import SurveySettings from '../components/SurveySettings.vue'
import type { LibraryQuestion, LibraryVersion, Question, QuestionEditInput, QuestionInput, QuestionType, QuestionValidation, Survey } from '../api/types'
import { canSelectLibraryQuestion } from '../utils/libraryPresentation'

interface OptionField { key: number; optionId?: string; label: string }

const route = useRoute()
const surveyId = String(route.params.id)
const survey = ref<Survey | null>(null)
const questions = ref<Question[]>([])
const sourceVersionNumbers = ref<Record<string, number>>({})
const type = ref<QuestionType>('single')
const title = ref('')
const required = ref(false)
let nextOptionId = 2
const optionFields = ref<OptionField[]>([{ key: 0, label: '' }, { key: 1, label: '' }])
const editingQuestionId = ref<string | null>(null)
const detachConfirmSignature = ref<string | null>(null)
const builderElement = ref<HTMLElement | null>(null)
// Vue's v-model.number returns an empty string when a number input is cleared.
const minSelections = ref<number | '' | null>(null)
const maxSelections = ref<number | '' | null>(null)
const minLength = ref<number | '' | null>(null)
const maxLength = ref<number | '' | null>(null)
const minValue = ref<number | '' | null>(null)
const maxValue = ref<number | '' | null>(null)
const integerOnly = ref(false)
const pending = ref(false)
const error = ref('')
const deleteQuestionId = ref<string | null>(null)
const questionNotice = ref('')
const deleteError = ref('')
const savedLibraryIds = ref<Record<string, string>>({})
const isChoice = computed(() => type.value === 'single' || type.value === 'multiple')
const editable = computed(() => canSelectLibraryQuestion(survey.value?.status))
const typeLabel: Record<QuestionType, string> = { single: '单选题', multiple: '多选题', text: '文本填空', number: '数字填空' }

function addOption() {
  optionFields.value.push({ key: nextOptionId++, label: '' })
}

function removeOption(key: number) {
  if (optionFields.value.length > 2) {
    optionFields.value = optionFields.value.filter((option) => option.key !== key)
  }
}

function resetForm() {
  editingQuestionId.value = null
  detachConfirmSignature.value = null
  type.value = 'single'
  title.value = ''
  required.value = false
  optionFields.value = [{ key: nextOptionId++, label: '' }, { key: nextOptionId++, label: '' }]
  minSelections.value = maxSelections.value = minLength.value = maxLength.value = minValue.value = maxValue.value = null
  integerOnly.value = false
  error.value = ''
}

async function saveToLibrary(question: Question) {
  if (pending.value) return
  pending.value = true; error.value = ''
  try {
    const saved = await idempotentApi<LibraryQuestion>(
      `import-survey-question:${question.id}`,
      `/surveys/${surveyId}/questions/${question.id}/save-to-library`,
      {},
    )
    savedLibraryIds.value[question.id] = saved.id
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '保存为可复用题目失败' }
  finally { pending.value = false }
}

function startEditing(question: Question) {
  deleteQuestionId.value = null
  editingQuestionId.value = question.id
  detachConfirmSignature.value = null
  type.value = question.type
  title.value = question.title
  required.value = question.required
  optionFields.value = question.options.length
    ? question.options.map((option) => ({ key: nextOptionId++, optionId: option.id, label: option.label }))
    : [{ key: nextOptionId++, label: '' }, { key: nextOptionId++, label: '' }]
  minSelections.value = question.validation.minSelections ?? null
  maxSelections.value = question.validation.maxSelections ?? null
  minLength.value = question.validation.minLength ?? null
  maxLength.value = question.validation.maxLength ?? null
  minValue.value = question.validation.minValue ?? null
  maxValue.value = question.validation.maxValue ?? null
  integerOnly.value = question.validation.integerOnly ?? false
  error.value = ''
  builderElement.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function refresh() {
  try {
    const [surveyResult, questionResult] = await Promise.all([
      api<Survey>(`/surveys/${surveyId}`),
      api<Question[]>(`/surveys/${surveyId}/questions`),
    ])
    survey.value = surveyResult
    questions.value = questionResult
    const logicalIds = [...new Set(questionResult.map((item) => item.sourceLibraryQuestionId).filter((id): id is string => !!id))]
    const histories = await Promise.all(logicalIds.map(async (id) => {
      try { return await api<LibraryVersion[]>(`/library/questions/${id}/versions`) }
      catch { return [] } // A revoked share leaves the snapshot and its version ID intact.
    }))
    sourceVersionNumbers.value = Object.fromEntries(histories.flat().map((version) => [version.id, version.versionNo]))
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取失败' }
}

async function deleteQuestion(question: Question) {
  if (pending.value) return
  if (deleteQuestionId.value !== question.id) {
    deleteError.value = ''
    deleteQuestionId.value = question.id
    return
  }
  pending.value = true
  deleteError.value = ''; questionNotice.value = ''
  try {
    await api<void>(`/surveys/${surveyId}/questions/${question.id}`, { method: 'DELETE' })
    questions.value = questions.value.filter((item) => item.id !== question.id)
    if (editingQuestionId.value === question.id) resetForm()
    deleteQuestionId.value = null
    await refresh()
    questionNotice.value = '已从这份草稿删除题目；题库原题和版本历史仍保留。'
  } catch (reason) {
    deleteError.value = reason instanceof Error ? reason.message : '删除结果不明，请刷新题目列表后确认'
  } finally { pending.value = false }
}

function replaceQuestion(updated: Question) {
  questions.value = questions.value.map((question) => question.id === updated.id ? updated : question)
}

async function submitQuestion() {
  error.value = ''
  const labels = isChoice.value ? optionFields.value.map((option) => option.label.trim()) : []
  if (isChoice.value && (labels.some((label) => !label) || new Set(labels).size !== labels.length)) {
    error.value = '请填写每个选项，且选项内容不能重复'
    return
  }
  pending.value = true
  const validation: QuestionValidation = {}
  if (type.value === 'multiple') {
    if (minSelections.value !== null && minSelections.value !== '') validation.minSelections = minSelections.value
    if (maxSelections.value !== null && maxSelections.value !== '') validation.maxSelections = maxSelections.value
  }
  if (type.value === 'text') {
    if (minLength.value !== null && minLength.value !== '') validation.minLength = minLength.value
    if (maxLength.value !== null && maxLength.value !== '') validation.maxLength = maxLength.value
  }
  if (type.value === 'number') {
    if (minValue.value !== null && minValue.value !== '') validation.minValue = minValue.value
    if (maxValue.value !== null && maxValue.value !== '') validation.maxValue = maxValue.value
    validation.integerOnly = integerOnly.value
  }
  try {
    if (editingQuestionId.value) {
      const payload: QuestionEditInput = {
        type: type.value, title: title.value, required: required.value, validation,
        options: isChoice.value ? optionFields.value.map((option) => ({
          ...(option.optionId ? { id: option.optionId } : {}), label: option.label.trim(),
        })) : [],
      }
      const original = questions.value.find((question) => question.id === editingQuestionId.value)
      const changedContent = original && (
        original.type !== payload.type || original.title !== payload.title.trim() ||
        original.required !== payload.required || JSON.stringify(original.options) !== JSON.stringify(payload.options) ||
        JSON.stringify(original.validation) !== JSON.stringify(payload.validation)
      )
      if (original?.sourceVersionId && changedContent) {
        const signature = JSON.stringify(payload)
        if (detachConfirmSignature.value !== signature) {
          detachConfirmSignature.value = signature
          return
        }
      }
      const item = await api<Question>(`/surveys/${surveyId}/questions/${editingQuestionId.value}`, {
        method: 'PUT', body: JSON.stringify(payload),
      })
      replaceQuestion(item)
      await refresh()
    } else {
      const payload: QuestionInput = {
        type: type.value, title: title.value, required: required.value, options: labels, validation,
      }
      const item = await api<Question>(`/surveys/${surveyId}/questions`, {
        method: 'POST', body: JSON.stringify(payload),
      })
      questions.value.push(item)
    }
    resetForm()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '添加失败' }
  finally { pending.value = false }
}

onMounted(() => { void refresh() })
</script>

<template>
  <div class="page-container editor-page">
    <RouterLink class="back-link" to="/surveys">← 返回我的问卷</RouterLink>
    <section v-if="survey" class="page-heading editor-heading">
      <div><span class="eyebrow">SURVEY EDITOR</span><h1>{{ survey.title }}</h1><p>{{ survey.description || '尚未添加问卷说明' }}</p></div>
      <div class="heading-count"><strong>{{ questions.length }}</strong><span>道题目</span></div>
    </section>
    <p v-if="error && !survey" class="form-error" role="alert">{{ error }}</p>
    <SurveySettings v-if="survey" :survey="survey" :question-count="questions.length" @updated="survey = $event" />
    <RouterLink v-if="survey" class="button button-outline editor-results-link" :to="`/surveys/${surveyId}/results`">查看统计结果 →</RouterLink>
    <LibraryPicker v-if="survey && editable" :survey-id="surveyId" @added="refresh" />
    <section v-if="survey && questions.some((item) => item.sourceVersionId)" class="card library-panel consent-section"><h2>跨问卷统计说明</h2><p class="notice">从题库选入的有效版本会自动参加该题目作者的跨问卷汇总。作者只能看到匿名门槛允许的聚合结果，不能读取本问卷原始答卷或填写者身份。</p></section>
    <div v-if="survey" class="editor-grid">
      <section class="question-list">
        <div class="list-topline"><h2>题目列表</h2><span>按作答顺序排列</span></div>
        <p v-if="questionNotice" class="notice" role="status">{{ questionNotice }}</p>
        <p v-if="deleteError" class="form-error" role="alert">{{ deleteError }}</p>
        <div v-if="questions.length === 0" class="card empty-card"><div class="empty-illustration">?</div><h3>从第一道题开始</h3><p>在右侧设置题型、题干和答案限制。</p></div>
        <article v-for="question in questions" :key="question.id" class="card question-card">
          <div class="question-meta"><span>Q{{ String(question.order).padStart(2, '0') }}</span><span>{{ typeLabel[question.type] }}</span><span v-if="question.required" class="required-tag">必答</span><button v-if="editable" type="button" class="edit-question-button" @click="startEditing(question)">编辑题目</button><button v-if="!question.sourceVersionId && !savedLibraryIds[question.id]" type="button" :disabled="pending" @click="saveToLibrary(question)">保存为可复用题目</button><RouterLink v-if="savedLibraryIds[question.id]" :to="`/library/questions/${savedLibraryIds[question.id]}`">已保存，查看题目</RouterLink></div>
          <h3>{{ question.title }}</h3>
          <div v-if="editable" class="question-delete-actions">
            <p v-if="deleteQuestionId === question.id" class="notice">确定从这份草稿删除“{{ question.title }}”？题库原题和版本历史仍保留。</p>
            <button type="button" class="button button-outline" :disabled="pending" @click="deleteQuestion(question)">{{ deleteQuestionId === question.id ? '确认删除此题' : '删除此题' }}</button>
            <button v-if="deleteQuestionId === question.id" type="button" :disabled="pending" @click="deleteQuestionId = null">取消</button>
          </div>
          <p v-if="question.sourceVersionId" class="source-note">来自题库题目 {{ question.sourceLibraryQuestionId }} · {{ sourceVersionNumbers[question.sourceVersionId] ? `版本 ${sourceVersionNumbers[question.sourceVersionId]}` : `版本 ID ${question.sourceVersionId}` }}。编辑内容后将脱离此来源；只修改跳转规则会保留来源。</p>
          <ul v-if="question.options.length" class="option-preview"><li v-for="option in question.options" :key="option.id"><span class="option-circle"></span>{{ option.label }}</li></ul>
          <p v-else class="input-preview">{{ question.type === 'number' ? '请填写数字答案' : '请填写文本答案' }}</p>
          <JumpRuleEditor :survey-id="surveyId" :question="question" :questions="questions" :editable="editable" @saved="replaceQuestion" />
        </article>
      </section>
      <aside ref="builderElement" class="card question-builder">
        <div class="section-heading"><span class="section-icon">✦</span><div><h2>{{ editingQuestionId ? '编辑题目' : '添加题目' }}</h2><p>{{ editingQuestionId ? '修改后保存到当前问卷' : '为问卷组织清晰的问题' }}</p></div></div>
        <p v-if="!editable" class="notice">问卷已发布，题目结构不可修改。</p>
        <p v-if="editable && editingQuestionId && questions.find((item) => item.id === editingQuestionId)?.sourceVersionId" class="notice">此题来自题库版本。修改题干、题型、必答、选项或校验配置后将脱离来源；仅修改跳转规则不会脱离。</p>
        <form v-if="editable" class="form-stack" @submit.prevent="submitQuestion">
          <label>题型<select v-model="type"><option value="single">单选题</option><option value="multiple">多选题</option><option value="text">文本填空</option><option value="number">数字填空</option></select></label>
          <label>题目内容<input v-model="title" required maxlength="500" placeholder="请输入题目" /></label>
          <div v-if="isChoice" class="option-builder">
            <div class="option-builder-heading"><span>选项</span><span class="optional">当前 {{ optionFields.length }} 个，至少保留 2 个</span></div>
            <div v-for="(option, index) in optionFields" :key="option.key" class="option-row">
              <label class="option-field">选项 {{ index + 1 }}<input v-model="option.label" required :placeholder="`请输入选项 ${index + 1}`" /></label>
              <button type="button" class="remove-option" :disabled="optionFields.length <= 2" :aria-label="`删除选项 ${index + 1}`" @click="removeOption(option.key)">删除</button>
            </div>
            <button type="button" class="add-option" @click="addOption">＋ 添加选项</button>
          </div>
          <template v-if="type === 'multiple'"><div class="two-fields"><label>最少选择<input v-model.number="minSelections" type="number" min="0" placeholder="不限" /></label><label>最多选择<input v-model.number="maxSelections" type="number" min="1" placeholder="不限" /></label></div></template>
          <template v-if="type === 'text'"><div class="two-fields"><label>最少字数<input v-model.number="minLength" type="number" min="0" placeholder="不限" /></label><label>最多字数<input v-model.number="maxLength" type="number" min="1" placeholder="不限" /></label></div></template>
          <template v-if="type === 'number'"><div class="two-fields"><label>最小值<input v-model.number="minValue" type="number" step="any" placeholder="不限" /></label><label>最大值<input v-model.number="maxValue" type="number" step="any" placeholder="不限" /></label></div><label class="check-row"><input v-model="integerOnly" type="checkbox" /><span>必须是整数</span></label></template>
          <label class="check-row"><input v-model="required" type="checkbox" /><span>此题必答</span></label>
          <p v-if="error" class="form-error" role="alert">{{ error }}</p>
          <p v-if="detachConfirmSignature" class="notice" role="alert">修改内容后，此问卷题目将脱离原题库版本。请再次点击确认保存；若继续修改内容，需重新确认。</p>
          <button class="button button-primary button-wide" :disabled="pending" type="submit">{{ pending ? '保存中…' : detachConfirmSignature ? '确认脱离并保存' : editingQuestionId ? '保存修改' : '添加到问卷' }}</button>
          <button v-if="editingQuestionId" class="cancel-edit-button" type="button" :disabled="pending" @click="resetForm">取消编辑</button>
        </form>
      </aside>
    </div>
  </div>
</template>
