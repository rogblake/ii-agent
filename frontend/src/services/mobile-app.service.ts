import type { ChatMessagePayload } from '@/typings/agent'
import { CommandType } from '@/typings/agent'

type SendMessageFn = (payload: ChatMessagePayload) => boolean

// Legacy flow params (app-specific password)
type SubmitToTestflightParams = {
    expoToken: string
    appleId: string
    appSpecificPassword: string
    teamId?: string
    sessionId: string
    sendMessage: SendMessageFn
}

// New flow params (stored credentials)
type SubmitToTestflightWithStoredCredsParams = {
    expoToken: string
    bundleIdentifier?: string
    sessionId: string
    sendMessage: SendMessageFn
}

// Apple auth params
type AppleAuthLoginParams = {
    appleId: string
    password: string
    sessionId: string
    sendMessage: SendMessageFn
}

type AppleAuth2FAParams = {
    code: string
    sessionId: string
    sendMessage: SendMessageFn
}

type AppleSelectTeamParams = {
    teamId: string
    sessionId: string
    sendMessage: SendMessageFn
}

type AppleAppSetupParams = {
    bundleIdentifier: string
    appName: string
    sessionId: string
    sendMessage: SendMessageFn
}

class MobileAppService {
    /**
     * Legacy flow: Submit to TestFlight with app-specific password
     */
    async submitToTestflight({
        expoToken,
        appleId,
        appSpecificPassword,
        teamId,
        sessionId,
        sendMessage
    }: SubmitToTestflightParams): Promise<void> {
        const payload: Record<string, unknown> = {
            expo_token: expoToken,
            apple_id: appleId,
            app_specific_password: appSpecificPassword
        }

        if (teamId) {
            payload.team_id = teamId
        }

        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.SUBMIT_TESTFLIGHT,
                ...payload
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error(
                'Socket.IO connection is not open. Please try again.'
            )
        }
    }

    /**
     * New flow: Submit to TestFlight using pre-authenticated Apple credentials
     */
    async submitToTestflightWithStoredCredentials({
        expoToken,
        bundleIdentifier,
        sessionId,
        sendMessage
    }: SubmitToTestflightWithStoredCredsParams): Promise<void> {
        const payload: Record<string, unknown> = {
            expo_token: expoToken,
            use_stored_credentials: true
        }

        if (bundleIdentifier) {
            payload.bundle_identifier = bundleIdentifier
        }

        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.SUBMIT_TESTFLIGHT,
                ...payload
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error(
                'Socket.IO connection is not open. Please try again.'
            )
        }
    }

    /**
     * Apple Auth: Initiate login with email and password
     */
    async appleAuthLogin({
        appleId,
        password,
        sessionId,
        sendMessage
    }: AppleAuthLoginParams): Promise<void> {
        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.APPLE_AUTH_LOGIN,
                apple_id: appleId,
                password: password
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error(
                'Socket.IO connection is not open. Please try again.'
            )
        }
    }

    /**
     * Apple Auth: Verify 2FA code
     */
    async appleAuth2FA({
        code,
        sessionId,
        sendMessage
    }: AppleAuth2FAParams): Promise<void> {
        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.APPLE_AUTH_2FA,
                code: code
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error(
                'Socket.IO connection is not open. Please try again.'
            )
        }
    }

    /**
     * Apple Auth: Select team
     */
    async appleSelectTeam({
        teamId,
        sessionId,
        sendMessage
    }: AppleSelectTeamParams): Promise<void> {
        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.APPLE_AUTH_SELECT_TEAM,
                team_id: teamId
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error(
                'Socket.IO connection is not open. Please try again.'
            )
        }
    }

    /**
     * Apple Auth: Setup app (bundle ID, certificates, profiles)
     */
    async appleAppSetup({
        bundleIdentifier,
        appName,
        sessionId,
        sendMessage
    }: AppleAppSetupParams): Promise<void> {
        const success = sendMessage({
            session_uuid: sessionId,
            content: {
                command: CommandType.APPLE_APP_SETUP,
                bundle_identifier: bundleIdentifier,
                app_name: appName
            } as ChatMessagePayload['content']
        })

        if (!success) {
            throw new Error(
                'Socket.IO connection is not open. Please try again.'
            )
        }
    }
}

export const mobileAppService = new MobileAppService()
