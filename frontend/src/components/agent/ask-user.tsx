'use client'

import { useState, useCallback } from 'react'
import { Check } from 'lucide-react'
import { useTranslation } from 'react-i18next'

export interface AskUserQuestion {
    id: string
    question: string
    options: string[]
    allowMultiple?: boolean
}

export interface AskUserData {
    title: string
    questions: AskUserQuestion[]
}

interface AskUserProps {
    data: AskUserData
    onSubmit: (answers: Record<string, string[]>) => void
    className?: string
    onSkip?: () => void
}

const AskUser = ({ data, onSubmit, onSkip, className }: AskUserProps) => {
    const { t } = useTranslation()
    const [selectedAnswers, setSelectedAnswers] = useState<
        Record<string, string[]>
    >({})

    const handleOptionSelect = useCallback(
        (questionId: string, option: string, allowMultiple?: boolean) => {
            setSelectedAnswers((prev) => {
                const currentSelections = prev[questionId] || []

                if (allowMultiple) {
                    // Toggle selection for multiple choice
                    if (currentSelections.includes(option)) {
                        return {
                            ...prev,
                            [questionId]: currentSelections.filter(
                                (o) => o !== option
                            )
                        }
                    }
                    return {
                        ...prev,
                        [questionId]: [...currentSelections, option]
                    }
                }

                // Single selection - replace
                return {
                    ...prev,
                    [questionId]: [option]
                }
            })
        },
        []
    )

    const handleSubmit = useCallback(() => {
        onSubmit(selectedAnswers)
    }, [selectedAnswers, onSubmit])

    const isOptionSelected = (questionId: string, option: string) => {
        return selectedAnswers[questionId]?.includes(option) || false
    }

    return (
        <div
            className={`w-full border border-grey max-w-2xl rounded-2xl bg-[#BEE6F02E] p-4 shadow-xl ${className}`}
        >
            <h2 className="mb-3 text-sm font-semibold text-white">
                {data.title}
            </h2>

            <div className="flex flex-col gap-6">
                {data.questions.map((q) => (
                    <div key={q.id} className="flex flex-col gap-3">
                        <p className="text-xs text-white/[0.56]">
                            {q.question}
                        </p>
                        <div className="flex flex-col gap-2">
                            {q.options.map((option, idx) => {
                                const isSelected = isOptionSelected(
                                    q.id,
                                    option
                                )
                                return (
                                    <button
                                        key={idx}
                                        onClick={() =>
                                            handleOptionSelect(
                                                q.id,
                                                option,
                                                q.allowMultiple
                                            )
                                        }
                                        className={`group relative flex items-center gap-3 rounded-lg px-3 py-2 text-left text-xs transition-all duration-200 ${
                                            isSelected
                                                ? 'bg-black text-white'
                                                : 'bg-[#0000004D] text-gray-200 hover:bg-[#333333]'
                                        }`}
                                    >
                                        <span className="flex-1 pr-6">
                                            {option}
                                        </span>
                                        {isSelected && (
                                            <Check className="absolute right-3 size-4 text-white" />
                                        )}
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                ))}
            </div>

            <div className="mt-6 flex items-center gap-4">
                <button
                    onClick={handleSubmit}
                    className="rounded-lg bg-sky-blue px-6 py-2.5 text-sm font-medium text-black transition-colors hover:bg-[#5ab0b0]"
                >
                    {t('common.submit')}
                </button>
                {onSkip && (
                    <button
                        onClick={onSkip}
                        className="px-4 text-sm text-white transition-colors hover:text-white"
                    >
                        {t('common.skip')}
                    </button>
                )}
            </div>
        </div>
    )
}

export default AskUser
