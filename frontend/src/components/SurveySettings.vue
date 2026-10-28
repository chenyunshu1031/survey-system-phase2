<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import type { Survey } from '../api/types'
import { formatBeijingInput, parseBeijingInput } from '../utils/beijingTime'

const props = defineProps<{ survey: Survey; questionCount: number }>()
const emit = defineEmits<{ updated: [survey: Survey] }>()
const title = ref('')
const description = ref('')
const deadline = ref('')
const allowAnonymous = ref(false)
const allowMultiple = ref(false)
const pending = ref(false)
const error = ref('')
const notice = ref('')
const confirmStatusAction = ref<'publish' | 'close' | null>(null)
const draft = computed(() => props.survey.status === 'draft')
const savedDeadlineExpired = computed(() => Boolean(props.survey.deadlineAt && new Date(props.survey.deadlineAt).getTime() <= Date.now()))
const hasUnsavedChanges = computed(() => {
  return title.value.trim() !== props.survey.title || description.value !== props.survey.description
    || deadline.value !== formatBeijingInput(props.survey.deadlineAt)
    || (draft.value && (allowAnonymous.value !== props.survey.allowAnonymous || allowMultiple.value !== props.survey.allowMultipleSubmissions))
})
const publicLink = computed(() => `${window.location.origin}/survey/${props.survey.slug}`)
const availabilityLabel: Record<Survey['availability'], string> = {
  draft: '未发布', open: '已发布 · 可访问', expired: '已截止', closed: '已关闭',
}

watch(() => props.survey, (survey) => {
  confirmStatusAction.value = null
  title.value = survey.title
  description.value = survey.description
  deadline.value = formatBeijingInput(survey.deadlineAt)
  allowAnonymous.value = survey.allowAnonymous
  allowMultiple.value = survey.allowMultipleSubmissions
}, { immediate: true })

async function saveSettings() {
  error.value = ''
  notice.value = ''
  pending.value = true
  try {
    const changes: Record<string, string | boolean | null> = {}
    if (title.value.trim() !== props.survey.title) changes.title = title.value.trim()
    if (description.value !== props.survey.description) changes.description = description.value
    if (deadline.value !== formatBeijingInput(props.survey.deadlineAt)) {
      changes.deadlineAt = deadline.value ? parseBeijingInput(deadline.value) : null
    }
    if (draft.value) {
      if (allowAnonymous.value !== props.survey.allowAnonymous) changes.allowAnonymous = allowAnonymous.value
      if (allowMultiple.value !== props.survey.allowMultipleSubmissions) changes.allowMultipleSubmissions = allowMultiple.value
    }
    if (!Object.keys(changes).length) { notice.value = '没有需要保存的修改'; return }
    const updated = await api<Survey>(`/surveys/${props.survey.id}`, {
      method: 'PATCH', body: JSON.stringify(changes),
    })
    emit('updated', updated)
    notice.value = '问卷设置已保存'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '保存失败'
  } finally { pending.value = false }
}

async function changeStatus(action: 'publish' | 'close') {
  if (confirmStatusAction.value !== action) {
    confirmStatusAction.value = action
    return
  }
  confirmStatusAction.value = null
  error.value = ''
  notice.value = ''
  pending.value = true
  try {
    const updated = await api<Survey>(`/surveys/${props.survey.id}/${action}`, { method: 'POST' })
    emit('updated', updated)
    notice.value = action === 'publish' ? '问卷已发布' : '问卷已关闭'
  } catch (reason) {
    error.value = reason instanceof Error ? reason.message : '操作失败'
  } finally { pending.value = false }
}
</script>

<template>
  <section class="card survey-settings">
    <div class="settings-heading"><div><span class="eyebrow">SURVEY SETTINGS</span><h2>问卷设置</h2></div><span class="status-badge">{{ availabilityLabel[survey.availability] }}</span></div>
    <form class="form-stack" @submit.prevent="saveSettings">
      <div class="settings-fields"><label>问卷标题<input v-model="title" required maxlength="160" /></label><label>截止时间 <span class="optional">可选 · 北京时间</span><input v-model="deadline" type="datetime-local" /></label></div>
      <label>问卷说明<textarea v-model="description" rows="2" maxlength="2000" /></label>
      <div class="settings-flags"><label class="check-row"><input v-model="allowAnonymous" type="checkbox" :disabled="!draft" /><span>允许匿名展示</span></label><label class="check-row"><input v-model="allowMultiple" type="checkbox" :disabled="!draft" /><span>允许重复填写</span></label></div>
      <p v-if="!draft" class="settings-hint">发布后，匿名与重复填写设置已锁定；标题、说明和截止时间仍可修改。</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p>
      <p v-if="notice" class="form-success" role="status">{{ notice }}</p>
      <p v-if="confirmStatusAction" class="settings-hint" role="alert">{{ confirmStatusAction === 'publish' ? '发布后题目结构、匿名和重复填写设置将锁定。请再次点击确认发布。' : '关闭后不能再次开放填写。请再次点击确认关闭。' }}</p>
      <div class="settings-actions"><button class="button button-primary" type="submit" :disabled="pending">保存设置</button><button v-if="draft" class="button button-outline" type="button" :disabled="pending || questionCount === 0 || savedDeadlineExpired || hasUnsavedChanges" @click="changeStatus('publish')">{{ confirmStatusAction === 'publish' ? '确认发布' : '发布问卷' }}</button><button v-else-if="survey.status === 'published'" class="button button-outline" type="button" :disabled="pending || hasUnsavedChanges" @click="changeStatus('close')">{{ confirmStatusAction === 'close' ? '确认关闭' : '关闭问卷' }}</button><button v-if="confirmStatusAction" class="button button-outline" type="button" :disabled="pending" @click="confirmStatusAction = null">取消</button></div>
      <p v-if="draft && questionCount === 0" class="settings-hint">至少添加一道题目后才能发布。</p>
      <p v-if="draft && savedDeadlineExpired" class="settings-hint">当前保存的截止时间已过；请修改为未来时间并先保存设置。</p>
      <p v-if="hasUnsavedChanges" class="settings-hint">请先保存设置，再操作问卷状态。</p>
    </form>
    <div v-if="!draft" class="share-link"><span>问卷访问链接</span><RouterLink :to="`/survey/${survey.slug}`">{{ publicLink }}</RouterLink><small>填写者需要先登录；问卷开放期间可通过此链接填写并提交。</small></div>
  </section>
</template>
