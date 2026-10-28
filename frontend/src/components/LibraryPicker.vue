<script setup lang="ts">
import { ref } from 'vue'
import { api } from '../api/client'
import type { BankItem, LibraryQuestion, LibraryVersion, QuestionBank } from '../api/types'

const props = defineProps<{ surveyId: string }>()
const emit = defineEmits<{ added: [] }>()
const open = ref(false)
const banks = ref<QuestionBank[]>([])
const bankId = ref('')
const items = ref<BankItem[]>([])
const own = ref<LibraryQuestion[]>([])
const shared = ref<LibraryQuestion[]>([])
const selected = ref<LibraryQuestion | null>(null)
const versions = ref<LibraryVersion[]>([])
const versionId = ref('')
const pending = ref(false)
const error = ref('')
const success = ref('')

async function toggle() {
  open.value = !open.value
  if (!open.value) return
  error.value = ''
  try {
    [banks.value, own.value, shared.value] = await Promise.all([
      api<QuestionBank[]>('/question-banks'), api<LibraryQuestion[]>('/library/questions'),
      api<LibraryQuestion[]>('/library/shared/questions'),
    ])
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取可选题目失败' }
}

async function loadBank() {
  if (!bankId.value) { items.value = []; return }
  try { items.value = await api<BankItem[]>(`/question-banks/${bankId.value}/items`) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '读取题库条目失败' }
}

async function choose(question: LibraryQuestion, preferredVersionId?: string) {
  selected.value = question
  versionId.value = preferredVersionId || question.currentVersionId
  success.value = ''; error.value = ''
  try { versions.value = await api<LibraryVersion[]>(`/library/questions/${question.id}/versions`) }
  catch (reason) { error.value = reason instanceof Error ? reason.message : '读取版本失败' }
}

function bankQuestion(item: BankItem): LibraryQuestion | undefined {
  return own.value.find((question) => question.id === item.libraryQuestionId)
}

async function add() {
  if (!selected.value || !versionId.value || pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/surveys/${props.surveyId}/questions/from-library`, { method: 'POST', body: JSON.stringify({
      libraryQuestionId: selected.value.id, versionId: versionId.value,
    }) })
    emit('added')
    success.value = '已创建新的问卷内题目快照，题目列表已刷新'
  } catch (reason) {
    if (reason instanceof TypeError) {
      emit('added')
      error.value = '连接中断，题目列表已重新读取。请先确认是否已选入，再决定是否再次选用。'
    } else error.value = reason instanceof Error ? reason.message : '选题失败'
  }
  finally { pending.value = false }
}
</script>

<template>
  <section class="card library-panel library-picker"><button class="library-toggle" type="button" :aria-expanded="open" @click="toggle">从题库选题 {{ open ? '收起' : '展开' }} ↓</button>
    <div v-if="open" class="library-picker-body">
      <p class="notice">每次选用都会创建新的问卷题目；后续库内版本变化不会改动本问卷快照。</p>
      <p v-if="error" class="form-error" role="alert">{{ error }}</p><p v-if="success" class="form-success" role="status">{{ success }}</p>
      <label class="library-field">个人题库<select v-model="bankId" @change="loadBank"><option value="">选择题库</option><option v-for="bank in banks" :key="bank.id" :value="bank.id">{{ bank.name }}</option></select></label>
      <div v-if="bankId" class="library-list"><p v-if="!items.length" class="notice">此题库暂无题目。</p><button v-for="item in items" :key="item.id" type="button" class="library-row" @click="bankQuestion(item) && choose(bankQuestion(item)!, item.selectedVersionId)">{{ item.selectedVersion.title }} <span>固定版本 {{ item.selectedVersion.versionNo }}</span></button></div>
      <h3>我的可复用题目</h3><div class="library-list"><button v-for="item in own" :key="item.id" type="button" class="library-row" @click="choose(item)">{{ item.currentVersion.title }} <span>选择版本 →</span></button><p v-if="!own.length" class="notice">暂无可复用题目。</p></div>
      <h3>获分享的题目</h3><div class="library-list"><button v-for="item in shared" :key="item.id" type="button" class="library-row" @click="choose(item)">{{ item.currentVersion.title }} <span>选择版本 →</span></button><p v-if="!shared.length" class="notice">暂无获分享题目。</p></div>
      <div v-if="selected" class="library-subcard form-stack"><strong>{{ selected.currentVersion.title }}</strong><label>选用版本<select v-model="versionId"><option v-for="version in versions" :key="version.id" :value="version.id">版本 {{ version.versionNo }} · {{ version.title }}</option></select></label><button class="button button-primary" type="button" :disabled="pending || !versions.length" @click="add">{{ pending ? '选入中…' : '选入这份草稿问卷' }}</button></div>
    </div>
  </section>
</template>
