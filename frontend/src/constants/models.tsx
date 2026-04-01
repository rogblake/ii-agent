import { IModel, ProviderType } from '@/typings/settings'

/**
 * BE Provider enum values (from agents/types.py).
 * FE must send these exact values to the BE.
 */
export const PROVIDER = {
    OPENAI: 'OpenAI' as ProviderType,
    ANTHROPIC: 'Anthropic' as ProviderType,
    GOOGLE: 'Google' as ProviderType,
    VERTEX_AI: 'VertexAI' as ProviderType,
    AZURE: 'Azure' as ProviderType,
    CEREBRAS: 'Cerebras' as ProviderType,
    CUSTOM: 'Custom' as ProviderType,
} as const

// Define available models for each provider
export const PROVIDER_MODELS: { [key: string]: IModel[] } = {
    anthropic: [
        {
            id: 'claude-sonnet-4-5-20250929',
            model: 'claude-sonnet-4-5-20250929',
            provider: PROVIDER.ANTHROPIC
        },
        {
            id: 'claude-sonnet-4-20250514',
            model: 'claude-sonnet-4-20250514',
            provider: PROVIDER.ANTHROPIC
        },
        {
            id: 'claude-opus-4-20250514',
            model: 'claude-opus-4-20250514',
            provider: PROVIDER.ANTHROPIC
        },
        {
            id: 'claude-3-7-sonnet-20250219',
            model: 'claude-3-7-sonnet-20250219',
            provider: PROVIDER.ANTHROPIC
        }
    ],
    openai: [
        {
            id: 'gpt-5',
            model: 'gpt-5',
            provider: PROVIDER.OPENAI
        },
        {
            id: 'gpt-5.2',
            model: 'gpt-5.2',
            provider: PROVIDER.OPENAI
        },
        {
            id: 'gpt-4.1',
            model: 'gpt-4.1',
            provider: PROVIDER.OPENAI
        },
        {
            id: 'gpt-4.5',
            model: 'gpt-4.5',
            provider: PROVIDER.OPENAI
        },
        {
            id: 'o3',
            model: 'o3',
            provider: PROVIDER.OPENAI
        },
        {
            id: 'o3-mini',
            model: 'o3-mini',
            provider: PROVIDER.OPENAI
        },
        {
            id: 'o4-mini',
            model: 'o4-mini',
            provider: PROVIDER.OPENAI
        },
        {
            id: 'custom',
            model: 'custom',
            provider: PROVIDER.OPENAI
        }
    ],
    gemini: [
        {
            id: 'gemini-3.1-pro-preview',
            model: 'gemini-3.1-pro-preview',
            provider: PROVIDER.GOOGLE
        },
        {
            id: 'gemini-3-pro-preview',
            model: 'gemini-3-pro-preview',
            provider: PROVIDER.GOOGLE
        },
        {
            id: 'gemini-2.5-flash',
            model: 'gemini-2.5-flash',
            provider: PROVIDER.GOOGLE
        },
        {
            id: 'gemini-2.5-pro',
            model: 'gemini-2.5-pro',
            provider: PROVIDER.GOOGLE
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
 * Maps BE Provider value (e.g. "Anthropic", "Google") to
 * the FE UI key used for logos and PROVIDERS_NAME lookup.
 */
const PROVIDER_TO_UI_KEY: Record<string, string> = {
    [PROVIDER.ANTHROPIC]: 'anthropic',
    [PROVIDER.OPENAI]: 'openai',
    [PROVIDER.GOOGLE]: 'gemini',
    [PROVIDER.VERTEX_AI]: 'vertex',
    [PROVIDER.AZURE]: 'azure',
    [PROVIDER.CEREBRAS]: 'cerebras',
    [PROVIDER.CUSTOM]: 'custom',
}

/** Resolve the FE UI key from a model's provider field. */
export function getProviderKey(model: { provider?: string }): string {
    if (model.provider) {
        return PROVIDER_TO_UI_KEY[model.provider] ?? 'custom'
    }
    return 'custom'
}
