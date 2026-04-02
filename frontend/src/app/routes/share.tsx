import { useEffect, useState } from 'react'
import { useParams } from 'react-router'
import { ShareAgentContent } from '@/components/share-agent-content'
import { ShareChatContent } from '@/components/share-chat-content'
import { sessionService } from '@/services/session.service'
import { ISession } from '@/typings/agent'
import { StorybookProvider } from '@/contexts/storybook-context'
import { StorybookModal } from '@/components/ui/storybook-modal'
import { SidebarProvider } from '@/components/ui/sidebar'

export function SharePage() {
    const { sessionId } = useParams()
    const [session, setSession] = useState<ISession | null>(null)

    useEffect(() => {
        const fetchSession = async () => {
            if (sessionId) {
                try {
                    const data = await sessionService.getPublicSession(sessionId)
                    setSession(data)
                } catch (error) {
                    console.error('Error fetching session:', error)
                    setSession(null)
                }
            }
        }

        fetchSession()
    }, [sessionId])

    if (session === null) {
        return null
    }

    if (session.agent_type === 'chat') {
        return (
            <StorybookProvider>
                <SidebarProvider>
                    <ShareChatContent />
                    <StorybookModal isShareMode={true} />
                </SidebarProvider>
            </StorybookProvider>
        )
    }

    return <ShareAgentContent />
}

export const Component = SharePage
