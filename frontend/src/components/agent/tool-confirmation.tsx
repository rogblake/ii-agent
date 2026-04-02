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

    const handleConfirm = (confirmed: boolean) => {
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
                }
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

        // Add more tool-specific cases here as needed
        // case TOOL.SOME_OTHER_TOOL: {
        //     return <SomeOtherToolConfirmation ... />
        // }

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
