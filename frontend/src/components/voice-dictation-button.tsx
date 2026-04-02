import { useCallback, useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Tooltip, TooltipContent, TooltipTrigger } from './ui/tooltip'
import ButtonIcon from './button-icon'
import clsx from 'clsx'

interface VoiceDictationButtonProps {
    textareaRef: React.RefObject<HTMLTextAreaElement | null>
    onTranscriptionChange?: (newValue: string) => void
    disabled?: boolean
}

// Type definitions for Web Speech API (not in all TypeScript libs)
interface SpeechRecognitionResult {
    readonly isFinal: boolean
    readonly length: number
    item(index: number): SpeechRecognitionAlternative
    [index: number]: SpeechRecognitionAlternative
}

interface SpeechRecognitionAlternative {
    readonly transcript: string
    readonly confidence: number
}

interface SpeechRecognitionResultList {
    readonly length: number
    item(index: number): SpeechRecognitionResult
    [index: number]: SpeechRecognitionResult
}

interface SpeechRecognitionEventType {
    readonly resultIndex: number
    readonly results: SpeechRecognitionResultList
}

interface SpeechRecognitionErrorEventType {
    readonly error: string
    readonly message: string
}

interface SpeechRecognitionInstance {
    continuous: boolean
    interimResults: boolean
    lang: string
    maxAlternatives: number
    onresult: ((event: SpeechRecognitionEventType) => void) | null
    onerror: ((event: SpeechRecognitionErrorEventType) => void) | null
    onend: (() => void) | null
    onaudiostart: (() => void) | null
    onspeechend: (() => void) | null
    start(): void
    stop(): void
    abort(): void
}

interface SpeechRecognitionConstructor {
    new (): SpeechRecognitionInstance
}

// Check for SpeechRecognition support
const SpeechRecognition: SpeechRecognitionConstructor | null =
    typeof window !== 'undefined'
        ? ((window as unknown as Record<string, unknown>)
              .SpeechRecognition as SpeechRecognitionConstructor) ||
          ((window as unknown as Record<string, unknown>)
              .webkitSpeechRecognition as SpeechRecognitionConstructor)
        : null

const VoiceDictationButton = ({
    textareaRef,
    onTranscriptionChange,
    disabled
}: VoiceDictationButtonProps) => {
    const { t, i18n } = useTranslation()
    const [isListening, setIsListening] = useState(false)
    const [isSupported, setIsSupported] = useState(false)
    const recognitionRef = useRef<SpeechRecognitionInstance | null>(null)

    // Check browser support on mount
    useEffect(() => {
        setIsSupported(!!SpeechRecognition)
    }, [])

    // Map i18n language to BCP-47 language tag for SpeechRecognition
    const getRecognitionLanguage = useCallback(() => {
        const langMap: Record<string, string> = {
            en: 'en-US',
            vi: 'vi-VN',
            ja: 'ja-JP',
            hi: 'hi-IN'
        }
        return langMap[i18n.language] || 'en-US'
    }, [i18n.language])

    const stopListening = useCallback(() => {
        if (recognitionRef.current) {
            recognitionRef.current.stop()
            recognitionRef.current = null
        }
        setIsListening(false)
    }, [])

    // Stop listening when button becomes disabled
    useEffect(() => {
        if (disabled && isListening) {
            stopListening()
        }
    }, [disabled, isListening, stopListening])

    const startListening = useCallback(() => {
        if (!SpeechRecognition || !textareaRef.current) return

        const recognition = new SpeechRecognition()
        recognition.continuous = false // Single utterance mode for better accuracy
        recognition.interimResults = false // Only use final results for better accuracy
        recognition.lang = getRecognitionLanguage()
        recognition.maxAlternatives = 3 // Get multiple alternatives to pick the best

        // Capture the original state ONCE at start
        const originalValue = textareaRef.current.value
        const insertPosition =
            textareaRef.current.selectionStart ?? originalValue.length
        const textBefore = originalValue.substring(0, insertPosition)
        const textAfter = originalValue.substring(insertPosition)

        // Add a space before the transcript if there's text before and no space
        const needsSpace =
            textBefore.length > 0 &&
            !textBefore.endsWith(' ') &&
            !textBefore.endsWith('\n')
        const prefix = needsSpace ? ' ' : ''

        recognition.onresult = (event: SpeechRecognitionEventType) => {
            // Get the best transcript from final results
            let transcript = ''

            for (let i = 0; i < event.results.length; i++) {
                const result = event.results[i]
                if (result.isFinal) {
                    // Pick the alternative with highest confidence
                    let bestAlternative = result[0]
                    for (let j = 1; j < result.length; j++) {
                        if (result[j].confidence > bestAlternative.confidence) {
                            bestAlternative = result[j]
                        }
                    }
                    transcript += bestAlternative.transcript
                }
            }

            if (textareaRef.current && transcript) {
                // Always reconstruct from the original base text
                const newValue = textBefore + prefix + transcript + textAfter

                textareaRef.current.value = newValue
                onTranscriptionChange?.(newValue)

                // Move cursor to end of transcribed text
                const newCursorPos =
                    textBefore.length + prefix.length + transcript.length
                textareaRef.current.setSelectionRange(
                    newCursorPos,
                    newCursorPos
                )
            }
        }

        recognition.onerror = (event: SpeechRecognitionErrorEventType) => {
            console.error('Speech recognition error:', event.error)
            stopListening()
        }

        recognition.onend = () => {
            setIsListening(false)
            recognitionRef.current = null
        }

        recognitionRef.current = recognition
        recognition.start()
        setIsListening(true)
    }, [
        textareaRef,
        getRecognitionLanguage,
        onTranscriptionChange,
        stopListening
    ])

    const toggleListening = useCallback(() => {
        if (isListening) {
            stopListening()
        } else {
            startListening()
        }
    }, [isListening, startListening, stopListening])

    // Cleanup on unmount
    useEffect(() => {
        return () => {
            if (recognitionRef.current) {
                recognitionRef.current.stop()
            }
        }
    }, [])

    // Don't render if not supported
    if (!isSupported) {
        return null
    }

    const tooltipText = isListening
        ? t('question.voiceInputListening')
        : t('question.voiceInput')

    return (
        <Tooltip>
            <TooltipTrigger asChild>
                <ButtonIcon
                    name="microphone"
                    onClick={toggleListening}
                    disabled={disabled}
                    className={clsx(
                        'transition-all',
                        isListening &&
                            'animate-pulse !bg-red-500 dark:!bg-red-500'
                    )}
                    iconClassName={clsx(
                        'text-black fill-none',
                        isListening && '!stroke-white !fill-transparent'
                    )}
                />
            </TooltipTrigger>
            <TooltipContent>{tooltipText}</TooltipContent>
        </Tooltip>
    )
}

export default VoiceDictationButton
