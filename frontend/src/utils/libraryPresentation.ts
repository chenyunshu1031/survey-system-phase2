import type { Survey } from '../api/types'

export function canManageLibrary(ownerId: string, userId: string | undefined): boolean {
  return !!userId && ownerId === userId
}

export function canSelectLibraryQuestion(status: Survey['status'] | undefined): boolean {
  return status === 'draft'
}

export function aggregateMetric(value: number | null, suppressed: boolean): string {
  return suppressed || value === null ? '样本不足' : String(value)
}
