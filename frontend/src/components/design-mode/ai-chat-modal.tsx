/**
 * AI Chat Modal Component
 *
 * A modal that appears when user double-clicks an element in design mode.
 * Allows user to describe changes they want AI to make.
 */

import { useState, useCallback, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { X, Send, Sparkles, Loader2 } from 'lucide-react'
import { cn } from '@/lib/utils'
import { Button } from '@/components/ui/button'
import { Textarea } from '@/components/ui/textarea'
import axiosInstance from '@/lib/axios'
import type { ElementInfo } from './types'

interface AIChatModalProps {
    isOpen: boolean
    element: ElementInfo | null
    sessionId?: string
    onClose: () => void
    onApplyChange: (change: AIChangeResult) => void
}

export interface AIChangeResult {
    designId: string
    changes: Array<{
        property: string
        value: string
    }>
    explanation: string
}

interface Message {
    role: 'user' | 'assistant'
    content: string
}

export function AIChatModal({
    isOpen,
    element,
    sessionId,
    onClose,
    onApplyChange,
}: AIChatModalProps) {
    const { t } = useTranslation()
    const [input, setInput] = useState('')
    const [messages, setMessages] = useState<Message[]>([])
    const [isLoading, setIsLoading] = useState(false)
    const textareaRef = useRef<HTMLTextAreaElement>(null)

    // Focus textarea when modal opens
    useEffect(() => {
        if (isOpen && textareaRef.current) {
            setTimeout(() => textareaRef.current?.focus(), 100)
        }
    }, [isOpen])

    // Reset state when element changes
    useEffect(() => {
        if (element) {
            setMessages([])
            setInput('')
        }
    }, [element?.designId])

    const handleSubmit = useCallback(async () => {
        if (!input.trim() || !element || !sessionId || isLoading) return

        const userMessage = input.trim()
        setInput('')
        setMessages((prev) => [...prev, { role: 'user', content: userMessage }])
        setIsLoading(true)

        try {
            const response = await axiosInstance.post('/v1/project/design/ai-change', {
                session_id: sessionId,
                element_info: {
                    designId: element.designId,
                    tagName: element.tagName,
                    className: element.className,
                    textContent: element.textContent.slice(0, 200),
                    computedStyles: element.computedStyles,
                    xpath: element.xpath,
                },
                user_request: userMessage,
            })

            const result = response.data

            setMessages((prev) => [
                ...prev,
                { role: 'assistant', content: result.explanation },
            ])

            // Apply the changes
            if (result.changes && result.changes.length > 0) {
                onApplyChange({
                    designId: element.designId,
                    changes: result.changes,
                    explanation: result.explanation,
                })
            }
        } catch (error) {
            console.error('[AIChatModal] Error:', error)
            setMessages((prev) => [
                ...prev,
                {
                    role: 'assistant',
                    content: t('designMode.aiChatModal.error'),
                },
            ])
        } finally {
            setIsLoading(false)
        }
    }, [input, element, sessionId, isLoading, onApplyChange, t])

    const handleKeyDown = useCallback(
        (e: React.KeyboardEvent) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                handleSubmit()
            }
        },
        [handleSubmit]
    )

    if (!isOpen || !element) return null

    // Build element description
    const elementDesc = `<${element.tagName}>${element.textContent.slice(0, 50)}${element.textContent.length > 50 ? '...' : ''}</${element.tagName}>`

    return (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/50 backdrop-blur-sm">
            <div
                className="w-full max-w-md mx-4 bg-[#1a1a24] border border-white/10 rounded-xl shadow-2xl overflow-hidden"
                onClick={(e) => e.stopPropagation()}
            >
                {/* Header */}
                <div className="flex items-center justify-between px-4 py-3 border-b border-white/10 bg-gradient-to-r from-purple-600/20 to-blue-600/20">
                    <div className="flex items-center gap-2">
                        <Sparkles className="h-4 w-4 text-purple-400" />
                        <span className="text-sm font-medium text-white">
                            {t('designMode.aiChatModal.title')}
                        </span>
                    </div>
                    <Button
                        variant="ghost"
                        size="icon"
                        className="h-7 w-7 text-gray-400 hover:text-white"
                        onClick={onClose}
                    >
                        <X className="h-4 w-4" />
                    </Button>
                </div>

                {/* Selected Element Info */}
                <div className="px-4 py-2 border-b border-white/10 bg-white/5">
                    <p className="text-xs text-gray-400">
                        {t('designMode.aiChatModal.selectedElementLabel')}
                    </p>
                    <p className="text-xs text-gray-300 font-mono truncate">{elementDesc}</p>
                </div>

                {/* Messages */}
                <div className="h-48 overflow-y-auto p-4 space-y-3">
                    {messages.length === 0 ? (
                        <div className="text-center text-gray-500 text-sm py-8">
                            <Sparkles className="h-8 w-8 mx-auto mb-2 text-purple-400/50" />
                            <p>{t('designMode.aiChatModal.emptyTitle')}</p>
                            <p className="text-xs mt-1">
                                {t('designMode.aiChatModal.emptyDescription')}
                            </p>
                        </div>
                    ) : (
                        messages.map((msg, i) => (
                            <div
                                key={i}
                                className={cn(
                                    'text-sm rounded-lg px-3 py-2 max-w-[85%]',
                                    msg.role === 'user'
                                        ? 'ml-auto bg-purple-600 text-white'
                                        : 'bg-white/10 text-gray-200'
                                )}
                            >
                                {msg.content}
                            </div>
                        ))
                    )}
                    {isLoading && (
                        <div className="flex items-center gap-2 text-gray-400 text-sm">
                            <Loader2 className="h-4 w-4 animate-spin" />
                            <span>{t('designMode.aiChatModal.thinking')}</span>
                        </div>
                    )}
                </div>

                {/* Input */}
                <div className="p-4 border-t border-white/10">
                    <div className="flex items-end gap-2">
                        <Textarea
                            ref={textareaRef}
                            value={input}
                            onChange={(e) => setInput(e.target.value)}
                            onKeyDown={handleKeyDown}
                            placeholder={t('designMode.aiChatModal.placeholder')}
                            className="flex-1 min-h-[40px] max-h-[100px] resize-none bg-white/5 border-white/10 text-white placeholder:text-gray-500"
                            disabled={isLoading}
                        />
                        <Button
                            size="icon"
                            className="h-10 w-10 bg-purple-600 hover:bg-purple-700"
                            onClick={handleSubmit}
                            disabled={!input.trim() || isLoading}
                        >
                            <Send className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </div>
        </div>
    )
}
