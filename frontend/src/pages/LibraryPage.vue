<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { RouterLink } from 'vue-router'
import { api } from '../api/client'
import { idempotentApi } from '../api/idempotency'
import type { BankItem, LibraryQuestion, LibraryVersion, QuestionBank, QuestionEditInput } from '../api/types'
import LibraryQuestionForm from '../components/LibraryQuestionForm.vue'
import { useAuthStore } from '../stores/auth'

const auth = useAuthStore()
const banks = ref<QuestionBank[]>([])
const questions = ref<LibraryQuestion[]>([])
const shared = ref<LibraryQuestion[]>([])
const selectedBankId = ref('')
const items = ref<BankItem[]>([])
const versions = ref<Record<string, LibraryVersion[]>>({})
const chosenVersions = ref<Record<string, string>>({})
const bankName = ref('')
const renamedBankName = ref('')
const deleteConfirmId = ref('')
const formKey = ref(0)
const pending = ref(false)
const error = ref('')
const success = ref('')

async function refresh() {
  try {
    [banks.value, questions.value, shared.value] = await Promise.all([
      api<QuestionBank[]>('/question-banks'), api<LibraryQuestion[]>('/library/questions'),
      api<LibraryQuestion[]>('/library/shared/questions'),
    ])
    if (selectedBankId.value) await loadBank(selectedBankId.value)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取题库失败' }
}

async function loadBank(bankId: string) {
  selectedBankId.value = bankId
    renamedBankName.value = banks.value.find((bank) => bank.id === bankId)?.name || ''
    deleteConfirmId.value = ''
  error.value = ''
  try {
    items.value = await api<BankItem[]>(`/question-banks/${bankId}/items`)
    const ids = [...new Set(items.value.map((item) => item.libraryQuestionId))]
    const pairs = await Promise.all(ids.map(async (id) => [id, await api<LibraryVersion[]>(`/library/questions/${id}/versions`)] as const))
    versions.value = Object.fromEntries(pairs)
    chosenVersions.value = Object.fromEntries(items.value.map((item) => [item.id, item.selectedVersionId]))
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '读取题库条目失败' }
}

async function renameSelectedBank() {
  if (!selectedBankId.value || pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/question-banks/${selectedBankId.value}`, {
      method: 'PATCH', body: JSON.stringify({ name: renamedBankName.value.trim() }),
    })
    await refresh()
    success.value = '题库已改名'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '题库改名失败' }
  finally { pending.value = false }
}

async function deleteSelectedBank() {
  if (!selectedBankId.value || pending.value) return
  if (deleteConfirmId.value !== selectedBankId.value) {
    deleteConfirmId.value = selectedBankId.value
    return
  }
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/question-banks/${selectedBankId.value}`, { method: 'DELETE' })
    selectedBankId.value = ''
    items.value = []
    deleteConfirmId.value = ''
    await refresh()
    success.value = '题库已移除；可复用题目、版本和问卷内容仍保留'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '移除题库失败' }
  finally { pending.value = false }
}

async function createBank() {
  if (pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await idempotentApi<QuestionBank>('create-bank', '/question-banks', { name: bankName.value.trim() })
    bankName.value = ''
    success.value = '题库已创建'
    await refresh()
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '创建题库失败' }
  finally { pending.value = false }
}

async function createQuestion(payload: QuestionEditInput) {
  if (pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    const created = await idempotentApi<LibraryQuestion>('create-question', '/library/questions', {
      type: payload.type, title: payload.title, required: payload.required,
      options: payload.options.map((item) => item.label), validation: payload.validation,
    })
    success.value = '可复用题目已创建'
    formKey.value += 1
    await refresh()
    // Keep the new question visible even if the list refresh was delayed.
    if (!questions.value.some((item) => item.id === created.id)) questions.value.unshift(created)
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '创建题目失败' }
  finally { pending.value = false }
}

async function removeItem(item: BankItem) {
  if (pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/question-banks/${item.bankId}/items/${item.libraryQuestionId}`, { method: 'DELETE' })
    await loadBank(item.bankId)
    success.value = '已从题库移除，不影响问卷中的题目'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '移除失败' }
  finally { pending.value = false }
}

async function switchVersion(item: BankItem) {
  const selectedVersionId = chosenVersions.value[item.id]
  if (!selectedVersionId || selectedVersionId === item.selectedVersionId || pending.value) return
  pending.value = true; error.value = ''; success.value = ''
  try {
    await api(`/question-banks/${item.bankId}/items/${item.libraryQuestionId}/version`, {
      method: 'PUT', body: JSON.stringify({ expectedVersionId: item.selectedVersionId, selectedVersionId }),
    })
    await loadBank(item.bankId)
    success.value = '题库条目已切换版本；现有问卷不变'
  } catch (reason) { error.value = reason instanceof Error ? reason.message : '版本切换失败，请刷新后重试' }
  finally { pending.value = false }
}

onMounted(() => { void auth.loadUser(); void refresh() })
</script>

<template>
  <div class="page-container library-page">
    <section class="page-heading"><div><span class="eyebrow">QUESTION LIBRARY</span><h1>个人题库</h1><p>保存可复用题目，按版本管理内容。</p></div></section>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <p v-if="success" class="form-success" role="status">{{ success }}</p>
    <div class="library-layout">
      <section class="card library-panel">
        <h2>我的题库</h2>
        <form class="form-stack" @submit.prevent="createBank"><label>新题库名称<input v-model="bankName" required maxlength="160" /></label><button class="button button-primary" :disabled="pending" type="submit">创建题库</button></form>
        <div class="library-list">
          <button v-for="bank in banks" :key="bank.id" class="library-row" type="button" :aria-pressed="selectedBankId === bank.id" @click="loadBank(bank.id)">{{ bank.name }} <span>查看条目 →</span></button>
          <p v-if="!banks.length" class="notice">还没有题库。</p>
        </div>
        <template v-if="selectedBankId">
          <div class="library-subcard form-stack">
            <form class="form-stack" @submit.prevent="renameSelectedBank"><label>题库名称<input v-model="renamedBankName" required maxlength="160" /></label><button type="submit" :disabled="pending">保存名称</button></form>
            <p class="notice">移除题库只隐藏这一组条目，不删除题目、版本或已选入问卷的快照。</p>
            <button type="button" :disabled="pending" @click="deleteSelectedBank">{{ deleteConfirmId === selectedBankId ? '再次点击确认移除题库' : '移除题库' }}</button>
          </div>
          <h3>题库条目</h3>
          <p v-if="!items.length" class="notice">当前题库为空。可在题目详情页加入题目。</p>
          <article v-for="item in items" :key="item.id" class="library-subcard">
            <RouterLink :to="`/library/questions/${item.libraryQuestionId}`">{{ item.selectedVersion.title }}</RouterLink>
            <p>固定选用版本 {{ item.selectedVersion.versionNo }}</p>
            <div class="library-actions"><label>所选版本<select v-model="chosenVersions[item.id]" :aria-label="`切换${item.selectedVersion.title}的版本`"><option v-for="version in versions[item.libraryQuestionId] || []" :key="version.id" :value="version.id">版本 {{ version.versionNo }} · {{ version.title }}</option></select></label><button type="button" :disabled="pending || chosenVersions[item.id] === item.selectedVersionId" @click="switchVersion(item)">确认切换</button><button type="button" :disabled="pending" @click="removeItem(item)">移除</button></div>
          </article>
        </template>
      </section>
      <div class="library-main">
        <section class="card library-panel"><h2>创建可复用题目</h2><LibraryQuestionForm :key="formKey" submit-label="创建题目" :pending="pending" @save="createQuestion" /></section>
        <section class="card library-panel"><h2>我的题目</h2><p v-if="!questions.length" class="notice">还没有可复用题目。</p><div class="library-list"><RouterLink v-for="item in questions" :key="item.id" class="library-row" :to="`/library/questions/${item.id}`">{{ item.currentVersion.title }} <span>版本 {{ item.currentVersion.versionNo }} →</span></RouterLink></div></section>
        <section class="card library-panel"><h2>获分享的题目</h2><p v-if="!shared.length" class="notice">暂无获分享题目。</p><div class="library-list"><RouterLink v-for="item in shared" :key="item.id" class="library-row" :to="`/library/questions/${item.id}`">{{ item.currentVersion.title }} <span>查看版本 →</span></RouterLink></div></section>
      </div>
    </div>
  </div>
</template>
