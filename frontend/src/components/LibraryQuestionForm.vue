<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import type { LibraryVersion, QuestionEditInput, QuestionType, QuestionValidation } from '../api/types'

const props = defineProps<{ baseVersion?: LibraryVersion | null; pending?: boolean; submitLabel: string }>()
const emit = defineEmits<{ save: [payload: QuestionEditInput] }>()
const type = ref<QuestionType>('single')
const title = ref('')
const required = ref(false)
const options = ref<{ id?: string; label: string }[]>([{ label: '' }, { label: '' }])
const minSelections = ref<number | ''>('')
const maxSelections = ref<number | ''>('')
const minLength = ref<number | ''>('')
const maxLength = ref<number | ''>('')
const minValue = ref<number | ''>('')
const maxValue = ref<number | ''>('')
const integerOnly = ref(false)
const error = ref('')
const isChoice = computed(() => type.value === 'single' || type.value === 'multiple')

watch(() => props.baseVersion, (base) => {
  type.value = base?.type || 'single'
  title.value = base?.title || ''
  required.value = base?.required || false
  options.value = base?.options.length ? base.options.map((item) => ({ ...item })) : [{ label: '' }, { label: '' }]
  minSelections.value = base?.validation.minSelections ?? ''
  maxSelections.value = base?.validation.maxSelections ?? ''
  minLength.value = base?.validation.minLength ?? ''
  maxLength.value = base?.validation.maxLength ?? ''
  minValue.value = base?.validation.minValue ?? ''
  maxValue.value = base?.validation.maxValue ?? ''
  integerOnly.value = base?.validation.integerOnly ?? false
  error.value = ''
}, { immediate: true })

function submit() {
  error.value = ''
  const labels = isChoice.value ? options.value.map((item) => item.label.trim()) : []
  if (isChoice.value && (labels.length < 2 || labels.some((label) => !label) || new Set(labels).size !== labels.length)) {
    error.value = '选择题至少需要两个不重复的非空选项'
    return
  }
  const validation: QuestionValidation = {}
  if (type.value === 'multiple') {
    if (minSelections.value !== '') validation.minSelections = Number(minSelections.value)
    if (maxSelections.value !== '') validation.maxSelections = Number(maxSelections.value)
  }
  if (type.value === 'text') {
    if (minLength.value !== '') validation.minLength = Number(minLength.value)
    if (maxLength.value !== '') validation.maxLength = Number(maxLength.value)
  }
  if (type.value === 'number') {
    if (minValue.value !== '') validation.minValue = Number(minValue.value)
    if (maxValue.value !== '') validation.maxValue = Number(maxValue.value)
    validation.integerOnly = integerOnly.value
  }
  emit('save', {
    type: type.value, title: title.value.trim(), required: required.value,
    options: isChoice.value ? options.value.map((item) => ({ ...(item.id ? { id: item.id } : {}), label: item.label.trim() })) : [],
    validation,
  })
}
</script>

<template>
  <form class="form-stack" @submit.prevent="submit">
    <label>题型<select v-model="type"><option value="single">单选题</option><option value="multiple">多选题</option><option value="text">文本填空</option><option value="number">数字填空</option></select></label>
    <label>题干<input v-model="title" required maxlength="500" /></label>
    <div v-if="isChoice" class="option-builder">
      <div class="option-builder-heading"><span>选项</span><span class="optional">选项 ID 在版本间保持不变</span></div>
      <div v-for="(option, index) in options" :key="index" class="option-row">
        <label class="option-field">选项 {{ index + 1 }}<input v-model="option.label" required /></label>
        <button class="remove-option" type="button" :disabled="options.length <= 2" @click="options.splice(index, 1)">删除</button>
      </div>
      <button class="add-option" type="button" @click="options.push({ label: '' })">＋ 添加选项</button>
    </div>
    <div v-if="type === 'multiple'" class="two-fields"><label>最少选择<input v-model.number="minSelections" type="number" min="0" /></label><label>最多选择<input v-model.number="maxSelections" type="number" min="1" /></label></div>
    <div v-if="type === 'text'" class="two-fields"><label>最少字数<input v-model.number="minLength" type="number" min="0" /></label><label>最多字数<input v-model.number="maxLength" type="number" min="1" /></label></div>
    <template v-if="type === 'number'"><div class="two-fields"><label>最小值<input v-model.number="minValue" type="number" step="any" /></label><label>最大值<input v-model.number="maxValue" type="number" step="any" /></label></div><label class="check-row"><input v-model="integerOnly" type="checkbox" /><span>必须是整数</span></label></template>
    <label class="check-row"><input v-model="required" type="checkbox" /><span>必答</span></label>
    <p v-if="error" class="form-error" role="alert">{{ error }}</p>
    <button class="button button-primary" type="submit" :disabled="pending">{{ pending ? '保存中…' : submitLabel }}</button>
  </form>
</template>
