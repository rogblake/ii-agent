import type { ChatMessagePayload } from '@/typings/agent'
import { CommandType } from '@/typings/agent'

type PublishProjectParams = {
    vercelApiKey: string
    sendMessage: (payload: ChatMessagePayload) => boolean
    sessionId: string
    projectName?: string
    projectPath?: string
    revision?: string
    envVars?: Array<{ name: string; value: string }>
}

type PublishCloudRunParams = {
    sendMessage: (payload: ChatMessagePayload) => boolean
    sessionId: string
    projectName?: string
    projectPath?: string
    revision?: string
    envVars?: Array<{ name: string; value: string }>
}

class FullstackService {
    async publishProject({
        vercelApiKey,
        sendMessage,
        sessionId,
        projectName,
        projectPath,
        revision,
        envVars
    }: PublishProjectParams): Promise<void> {
        const payload: Record<string, unknown> = {
            vercel_api_key: vercelApiKey
        }

        if (projectName) {
            payload.project_name = projectName
        }

        if (projectPath) {
            payload.project_path = projectPath
        }

        if (revision) {
            payload.revision = revision
        }

        if (Array.isArray(envVars) && envVars.length > 0) {
            payload.env_vars = envVars
        }

        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.PUBLISH_PROJECT,
                ...payload
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error('Socket.IO connection is not open. Please try again.')
        }
    }

    async publishCloudRun({
        sendMessage,
        sessionId,
        projectName,
        projectPath,
        revision,
        envVars
    }: PublishCloudRunParams): Promise<void> {
        const payload: Record<string, unknown> = {}

        if (projectName) {
            payload.project_name = projectName
        }

        if (projectPath) {
            payload.project_path = projectPath
        }

        if (revision) {
            payload.revision = revision
        }

        if (Array.isArray(envVars) && envVars.length > 0) {
            payload.env_vars = envVars
        }

        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.PUBLISH_CLOUD_RUN,
                ...payload
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error('Socket.IO connection is not open. Please try again.')
        }
    }
}

export const fullstackService = new FullstackService()
