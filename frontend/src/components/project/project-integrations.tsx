import { RevenueCatConnection } from '@/components/settings/revenuecat-connection'
import { AGENT_TYPE } from '@/typings/agent'
import { SupabaseConnection } from './supabase-connection'

interface ProjectIntegrationsProps {
    agentType?: string
}

const ProjectIntegrations = ({ agentType }: ProjectIntegrationsProps) => {
    const showRevenueCat = agentType === AGENT_TYPE.MOBILE_APP

    return (
        <div className="space-y-4">
            <SupabaseConnection />
            {showRevenueCat ? <RevenueCatConnection variant="project" /> : null}
        </div>
    )
}

export default ProjectIntegrations
