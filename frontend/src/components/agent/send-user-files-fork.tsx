import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { GlobeIcon } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { ForkSessionDialog } from '@/components/fork-session-dialog'
import type { ForkType } from '@/typings/session'

// Valid source agent types that can trigger fork to website
const VALID_FORK_SOURCE_AGENT_TYPES = ['deep_research', 'fast_research']

interface SendUserFilesForkProps {
    sessionId: string
    attachments: string[]
    isResult: boolean
    agentType?: string
}

export function SendUserFilesFork({
    sessionId,
    attachments,
    isResult,
    agentType
}: SendUserFilesForkProps) {
    const { t } = useTranslation()
    const [showForkDialog, setShowForkDialog] = useState(false)
    const [forkType, setForkType] = useState<ForkType>('research_to_website')

    // Only show fork button when:
    // 1. Tool has completed (isResult)
    // 2. There are attachments
    // 3. Agent type is valid for forking (deep_research or fast_research)
    if (!isResult || !attachments || attachments.length === 0) {
        return null
    }

    if (!agentType || !VALID_FORK_SOURCE_AGENT_TYPES.includes(agentType)) {
        return null
    }

    return (
        <>
            <div className="flex gap-2 mt-2">
                <Button
                    variant="outline"
                    size="sm"
                    className="gap-2 bg-[rgb(45,45,45)] hover:bg-[rgb(55,55,55)] text-white border-gray-600"
                    onClick={(e) => {
                        e.stopPropagation()
                        setForkType('research_to_website')
                        setShowForkDialog(true)
                    }}
                >
                    <GlobeIcon className="size-4" />
                    {t('fork.createWebsite.button')}
                </Button>
                {/* Future: Add more fork options like slide */}
            </div>

            <ForkSessionDialog
                open={showForkDialog}
                onOpenChange={setShowForkDialog}
                sessionId={sessionId}
                attachments={attachments}
                forkType={forkType}
            />
        </>
    )
}
