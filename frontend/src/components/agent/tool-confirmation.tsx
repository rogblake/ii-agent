'use client'

import { Check, X } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Button } from '../ui/button'
import { ToolConfirmationData, TOOL } from '@/typings/agent'
import { useSocketIOContext } from '@/contexts/websocket-context'
import { useAppDispatch } from '@/state'
import { setRunStatus } from '@/state/slice/agent'
import { setLoading } from '@/state/slice/ui'
import { SecretsInput } from './secrets-input'

interface ToolConfirmationProps {
    confirmation: ToolConfirmationData
}

export function ToolConfirmation({ confirmation }: ToolConfirmationProps) {
    const { t } = useTranslation()
    const { sendMessage } = useSocketIOContext()
    const dispatch = useAppDispatch()
    const [isResponding, setIsResponding] = useState(false)

    // Get tool info from the first active requirement
    const requirement = confirmation.active_requirements[0]
    const toolName =
        requirement?.tool_execution?.tool_name ||
        t('agent.toolConfirmation.unknownTool')
    const toolArgs = requirement?.tool_execution?.tool_args || {}

    const handleConfirm = (
        confirmed: boolean,
        userInput?: Record<string, unknown>
    ) => {
        if (isResponding) return

        setIsResponding(true)
        dispatch(setRunStatus('running'))
        dispatch(setLoading(true))

        // Send continue_run command to backend
        sendMessage({
            type: 'continue_run',
            content: {
                run_id: confirmation.run_id,
                session_id: confirmation.session_id,
                confirmed: confirmed,
                tool: {
                    tool_id: requirement?.tool_execution?.tool_call_id || '',
                    tool_name: requirement?.tool_execution?.tool_name || ''
                },
                ...(userInput ? { user_input: userInput } : {})
            }
        })
    }

    // Show processing state when responding
    if (isResponding) {
        return (
            <div className="mt-3 flex items-center gap-2 text-sm text-gray-500">
                <div className="animate-pulse">
                    {t('agent.toolConfirmation.processingResponse')}
                </div>
            </div>
        )
    }

    // Render tool-specific confirmation UI based on tool type
    switch (toolName) {
        case TOOL.ASK_USER_ENV: {
            const requestedKeys =
                (
                    toolArgs as {
                        requested_keys?: Array<{
                            key: string
                            description?: string
                        }>
                    }
                )?.requested_keys || []
            const message = (toolArgs as { message?: string })?.message

            return (
                <SecretsInput
                    secrets={requestedKeys.map((item) => ({
                        key: item.key,
                        value: '',
                        description: item.description
                    }))}
                    message={message}
                    sessionId={confirmation.session_id}
                    onConfirm={handleConfirm}
                    onCancel={() => handleConfirm(false)}
                />
            )
        }

        case TOOL.ASK_USER_SELECT: {
            return (
                <AskUserSelectUI
                    toolArgs={toolArgs}
                    onSelect={(selected) =>
                        handleConfirm(true, { selected })
                    }
                    onSkip={() => handleConfirm(false)}
                />
            )
        }

        default:
            // Default confirmation UI for generic tools
            return (
                <div className="mt-3 border border-gray-300 dark:border-gray-700 rounded-lg p-4 bg-white dark:bg-[#1e1e1e]">
                    <div className="mb-3">
                        <div className="text-sm font-medium text-gray-900 dark:text-gray-100 mb-1">
                            {t('agent.toolConfirmation.tool')}: {toolName}
                        </div>
                        {Object.keys(toolArgs).length > 0 && (
                            <div className="text-xs text-gray-600 dark:text-gray-400 mt-2">
                                <details className="cursor-pointer">
                                    <summary className="hover:text-gray-800 dark:hover:text-gray-200">
                                        {t(
                                            'agent.toolConfirmation.viewArguments'
                                        )}
                                    </summary>
                                    <pre className="mt-2 p-2 bg-gray-100 dark:bg-[#2d2d2d] rounded text-xs overflow-x-auto">
                                        {JSON.stringify(toolArgs, null, 2)}
                                    </pre>
                                </details>
                            </div>
                        )}
                    </div>

                    <div className="flex gap-3">
                        <Button
                            onClick={() => handleConfirm(true)}
                            className="flex-1 bg-green-600 hover:bg-green-700 text-white font-medium py-2 px-4 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2"
                            disabled={isResponding}
                        >
                            <Check className="size-4" />
                            {t('agent.toolConfirmation.yesContinue')}
                        </Button>
                        <Button
                            onClick={() => handleConfirm(false)}
                            variant="outline"
                            className="flex-1 border-red-300 dark:border-red-700 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-900/20 font-medium py-2 px-4 rounded-lg transition-colors duration-200 flex items-center justify-center gap-2"
                            disabled={isResponding}
                        >
                            <X className="size-4" />
                            {t('agent.toolConfirmation.noCancel')}
                        </Button>
                    </div>
                </div>
            )
    }
}

// --- AskUserSelect UI ---

interface AskUserSelectOption {
    value: string
    label: string
}

interface AskUserSelectUIProps {
    toolArgs: Record<string, unknown>
    onSelect: (selected: string) => void
    onSkip: () => void
}

function AskUserSelectUI({ toolArgs, onSelect, onSkip }: AskUserSelectUIProps) {
    const { t } = useTranslation()
    const [selectedValue, setSelectedValue] = useState<string | null>(null)

    const question = (toolArgs.question as string) || ''
    const options = (toolArgs.options as AskUserSelectOption[]) || []

    return (
        <div className="mt-3 w-full max-w-2xl rounded-2xl border border-gray-200 dark:border-gray-700 bg-white dark:bg-[#1e1e1e] p-4 shadow-sm">
            <p className="mb-3 text-sm font-medium text-gray-900 dark:text-gray-100">
                {question}
            </p>

            <div className="flex flex-col gap-2">
                {options.map((option, idx) => {
                    const isSelected = selectedValue === option.value
                    return (
                        <button
                            key={idx}
                            onClick={() => setSelectedValue(option.value)}
                            className={`group relative flex items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-all duration-200 ${
                                isSelected
                                    ? 'bg-sky-100 dark:bg-sky-900/30 border border-sky-400 dark:border-sky-600 text-sky-900 dark:text-sky-100'
                                    : 'bg-gray-50 dark:bg-[#2d2d2d] border border-gray-200 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-[#333333]'
                            }`}
                        >
                            <span className="flex-1">{option.label}</span>
                            {isSelected && (
                                <Check className="size-4 text-sky-600 dark:text-sky-400" />
                            )}
                        </button>
                    )
                })}
            </div>

            <div className="mt-4 flex items-center gap-3">
                <Button
                    onClick={() => {
                        if (selectedValue) onSelect(selectedValue)
                    }}
                    disabled={!selectedValue}
                    className="bg-sky-600 hover:bg-sky-700 text-white font-medium py-2 px-6 rounded-lg transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                    {t('common.confirm')}
                </Button>
                <button
                    onClick={onSkip}
                    className="px-4 py-2 text-sm text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 transition-colors"
                >
                    {t('common.skip')}
                </button>
            </div>
        </div>
    )
}
