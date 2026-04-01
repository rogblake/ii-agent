import { IModel } from '@/typings/settings'

// Define available models for each provider
export const PROVIDER_MODELS: { [key: string]: IModel[] } = {
    anthropic: [
        {
            id: 'claude-sonnet-4-5-20250929',
            model: 'claude-sonnet-4-5-20250929',
            api_type: 'anthropic'
        },
        {
            id: 'claude-sonnet-4-20250514',
            model: 'claude-sonnet-4-20250514',
            api_type: 'anthropic'
        },
        {
            id: 'claude-opus-4-20250514',
            model: 'claude-opus-4-20250514',
            api_type: 'anthropic'
        },
        {
            id: 'claude-3-7-sonnet-20250219',
            model: 'claude-3-7-sonnet-20250219',
            api_type: 'anthropic'
        }
    ],
    openai: [
        {
            id: 'gpt-5',
            model: 'gpt-5',
            api_type: 'openai'
        },
        {
            id: 'gpt-5.2',
            model: 'gpt-5.2',
            api_type: 'openai'
        },
        {
            id: 'gpt-4.1',
            model: 'gpt-4.1',
            api_type: 'openai'
        },
        {
            id: 'gpt-4.5',
            model: 'gpt-4.5',
            api_type: 'openai'
        },
        {
            id: 'o3',
            model: 'o3',
            api_type: 'openai'
        },
        {
            id: 'o3-mini',
            model: 'o3-mini',
            api_type: 'openai'
        },
        {
            id: 'o4-mini',
            model: 'o4-mini',
            api_type: 'openai'
        },
        {
            id: 'custom',
            model: 'custom',
            api_type: 'openai'
        }
    ],
    gemini: [
        {
            id: 'gemini-3.1-pro-preview',
            model: 'gemini-3.1-pro-preview',
            api_type: 'gemini'
        },
        {
            id: 'gemini-3-pro-preview',
            model: 'gemini-3-pro-preview',
            api_type: 'gemini'
        },
        {
            id: 'gemini-2.5-flash',
            model: 'gemini-2.5-flash',
            api_type: 'gemini'
        },
        {
            id: 'gemini-2.5-pro',
            model: 'gemini-2.5-pro',
            api_type: 'gemini'
        }
    ],
    custom: []
}

export const PROVIDERS_NAME: { [key: string]: string } = {
    anthropic: 'Anthropic',
    openai: 'OpenAI',
    gemini: 'Gemini',
    vertex: 'Vertex',
    azure: 'Azure',
    custom: 'Custom'
}

/**
 * Maps BE provider display name (e.g. "Anthropic", "Google") to
 * the FE key used for logos and PROVIDERS_NAME lookup.
 */
const PROVIDER_TO_KEY: Record<string, string> = {
    anthropic: 'anthropic',
    openai: 'openai',
    google: 'gemini',
    gemini: 'gemini',
    vertex: 'vertex',
    azure: 'azure',
    custom: 'custom',
}

/** Resolve the FE provider key from a model's provider or api_type field. */
export function getProviderKey(model: { provider?: string; api_type?: string }): string {
    if (model.provider) {
        const key = PROVIDER_TO_KEY[model.provider.toLowerCase()]
        if (key) return key
    }
    if (model.api_type) {
        return model.api_type
    }
    return 'custom'
}
