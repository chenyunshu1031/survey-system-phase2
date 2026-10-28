export type QuestionType = 'single' | 'multiple' | 'text' | 'number'

export interface Survey {
  id: string
  ownerId: string
  slug: string
  title: string
  description: string
  allowAnonymous: boolean
  allowMultipleSubmissions: boolean
  status: 'draft' | 'published' | 'closed'
  availability: 'draft' | 'open' | 'expired' | 'closed'
  deadlineAt: string | null
  createdAt: string
  updatedAt: string
  publishedAt: string | null
  closedAt: string | null
}

export interface PublicSurvey {
  slug: string
  title: string
  description: string
  allowAnonymous: boolean
  allowMultipleSubmissions: boolean
  availability: Survey['availability']
  deadlineAt: string | null
  hasSubmitted: boolean
}

export type JumpOperator = 'equals' | 'containsAny' | 'containsAll' | 'eq' | 'gt' | 'gte' | 'lt' | 'lte' | 'between'

export interface JumpRule {
  id: string
  priority: number
  targetQuestionId: string
  operator: JumpOperator
  optionIds: string[]
  value?: number
  minValue?: number
  maxValue?: number
}

export interface QuestionValidation {
  minSelections?: number
  maxSelections?: number
  minLength?: number
  maxLength?: number
  minValue?: number
  maxValue?: number
  integerOnly?: boolean
}

export interface Question {
  id: string
  surveyId: string
  order: number
  type: QuestionType
  title: string
  required: boolean
  options: { id: string; label: string }[]
  validation: QuestionValidation
  jumpRules: JumpRule[]
  jumpRuleWarnings?: string[]
  sourceLibraryQuestionId?: string
  sourceVersionId?: string
}

export interface QuestionInput {
  type: QuestionType
  title: string
  required: boolean
  options: string[]
  validation: QuestionValidation
}

export interface QuestionEditInput extends Omit<QuestionInput, 'options'> {
  options: { id?: string; label: string }[]
}

export interface QuestionStatistics extends Question {
  reachedCount: number
  answeredCount: number
  optionCounts?: { optionId: string; label: string; count: number }[]
  entries?: { value: string | number; submittedAt: string; respondent: string }[]
  hasMoreEntries?: boolean
  average?: number | null
}

export interface SurveyStatistics {
  surveyId: string
  responseCount: number
  asOf: string
  submissionRevision: number
  questions: QuestionStatistics[]
}

export interface LibraryVersion {
  id: string
  libraryQuestionId: string
  versionNo: number
  parentVersionId: string | null
  createdById: string
  type: QuestionType
  title: string
  required: boolean
  options: { id: string; label: string }[]
  validation: QuestionValidation
  createdAt: string
}

export interface LibraryQuestion {
  id: string
  ownerId: string
  currentVersionId: string
  currentVersion: LibraryVersion
  createdAt: string
  updatedAt: string
}

export interface QuestionBank { id: string; name: string; createdAt: string; updatedAt: string }

export interface BankItem {
  id: string
  bankId: string
  libraryQuestionId: string
  selectedVersionId: string
  selectedVersion: LibraryVersion
  createdAt: string
  updatedAt: string
}

export interface QuestionShare { recipientUserId: string; recipientUsername: string | null; createdAt: string }

export interface QuestionUsage {
  surveyId: string
  questionId: string
  versionId: string
  status: Survey['status']
  isOwnSurvey: boolean
}

export interface CrossSurveyStatistics {
  scope: 'owned_surveys_and_explicit_consent' | 'all_surveys'
  participatingSurveyCount: number
  suppression: { applied: boolean; minimumDistinctRespondents: number }
  responseCount: number | null
  reachedCount: number | null
  answeredCount: number | null
  optionCounts?: { optionId: string; count: number }[] | null
  textAnswerCounts?: { value: string; count: number }[] | null
  average?: number | null
  numericDistribution?: {
    lowerBound: number
    upperBound: number
    upperInclusive: boolean
    count: number
  }[] | null
}

export interface CrossSurveyOverview {
  groups: { versionIds: string[]; versionNumbers: number[]; statistics: CrossSurveyStatistics }[]
}
