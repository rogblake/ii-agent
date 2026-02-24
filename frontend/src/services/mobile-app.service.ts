type SendMessageFn = (payload: {
    type: string
    content: Record<string, unknown>
}) => boolean

// Legacy flow params (app-specific password)
type SubmitToTestflightParams = {
    expoToken: string
    appleId: string
    appSpecificPassword: string
    teamId?: string
    sendMessage: SendMessageFn
}

// New flow params (stored credentials)
type SubmitToTestflightWithStoredCredsParams = {
    expoToken: string
    bundleIdentifier?: string
    sendMessage: SendMessageFn
}

// Apple auth params
type AppleAuthLoginParams = {
    appleId: string
    password: string
    sendMessage: SendMessageFn
}

type AppleAuth2FAParams = {
    code: string
    sendMessage: SendMessageFn
}

type AppleSelectTeamParams = {
    teamId: string
    sendMessage: SendMessageFn
}

type AppleAppSetupParams = {
    bundleIdentifier: string
    appName: string
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
            type: 'submit_testflight',
            content: payload
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
            type: 'submit_testflight',
            content: payload
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
        sendMessage
    }: AppleAuthLoginParams): Promise<void> {
        const success = sendMessage({
            type: 'apple_auth_login',
            content: {
                apple_id: appleId,
                password: password
            }
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
    async appleAuth2FA({ code, sendMessage }: AppleAuth2FAParams): Promise<void> {
        const success = sendMessage({
            type: 'apple_auth_2fa',
            content: {
                code: code
            }
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
        sendMessage
    }: AppleSelectTeamParams): Promise<void> {
        const success = sendMessage({
            type: 'apple_auth_select_team',
            content: {
                team_id: teamId
            }
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
        sendMessage
    }: AppleAppSetupParams): Promise<void> {
        const success = sendMessage({
            type: 'apple_app_setup',
            content: {
                bundle_identifier: bundleIdentifier,
                app_name: appName
            }
        })

        if (!success) {
            throw new Error(
                'Socket.IO connection is not open. Please try again.'
            )
        }
    }
}

export const mobileAppService = new MobileAppService()
