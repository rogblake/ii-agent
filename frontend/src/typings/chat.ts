import type { ChatMediaType } from '@/constants/media-type-config'
import type { StorybookGenre, StorybookLanguage } from '@/typings/media-types'
import { StorybookContext, VideoFrameReference, VideoSettings } from './agent'

export interface GitHubRepositoryContext {
    owner: string
    name: string
    full_name: string
    default_branch: string
}

export type MediaReferenceType = 'subject' | 'scene' | 'style'

export interface MediaReference {
    file_id: string
    type?: MediaReferenceType | null
}

export interface AdvancedModeReference extends MediaReference {
    file_url?: string
}

export interface AdvancedModeSettings {
    enabled: boolean
    references: AdvancedModeReference[]
}

export interface ChatQueryPayload {
    session_id?: string
    model_id: string
    text: string
    files: string[]
    tools?: {
        web_search: boolean
        web_visit: boolean
        image_search: boolean
        code_interpreter?: boolean
        generate_image?: boolean
        generate_video?: boolean
    }
    media_preferences?: {
        enabled: boolean
        type: ChatMediaType
        model_name: string
        provider?: string
        aspect_ratio?: string
        resolution?: string
        page_count?: number | 'unlimited'
        text_position?: string
        language?: StorybookLanguage
        genre?: StorybookGenre
        manga_layout?: boolean
        rich_dialogue?: boolean
        voice_enabled?: boolean
        references?: MediaReference[]
        mini_tools?: {
            id: string
            name: string
            reference_file_ids?: string[]
        }
        template_id?: string
        video_settings?: VideoSettings
        video_frames?: VideoFrameReference[]
        advanced_mode?: boolean
        storybook_context?: StorybookContext
    }
    github_repository?: GitHubRepositoryContext
}

export type ChatStreamEvent =
    | {
          type: 'session'
          session_id: string
          is_new_session?: boolean
          name?: string
          agent_type?: string
          model_id?: string
          created_at?: string
      }
    | {
          type: 'content_start'
      }
    | {
          type: 'token'
          content: string
      }
    | {
          type: 'thinking'
          status: 'delta'
          delta: string
          signature?: string
      }
    | {
          type: 'tool_call_start'
          id: string
          name: string
          call_type: string
      }
    | {
          type: 'tool_call_delta'
          id: string
          delta: string
      }
    | {
          type: 'tool_call_stop'
          id: string
          name: string
          input: string
      }
    | {
          type: 'tool_result'
          tool_call_id: string
          name: string
          output: string
          is_error?: boolean
      }
    | {
          type: 'tool_progress'
          tool_call_id: string
          name: string
          output: string
      }
    | {
          type: 'usage'
          input_tokens: number
          output_tokens: number
          cache_creation_tokens: number
          cache_read_tokens: number
          total_tokens: number
      }
    | {
          type: 'complete'
          message_id?: string
          finish_reason?: string
          elapsed_ms?: number
      }
    | {
          type: 'done'
      }
    | {
          type: 'error'
          message?: string
          code?: string
      }

export interface ChatStreamOptions {
    signal?: AbortSignal
    onEvent: (event: ChatStreamEvent) => void
}

export type ContentPart =
    | {
          type: 'text'
          text: string
      }
    | {
          type: 'reasoning'
          id?: string
          thinking: string
          signature?: string
          started_at?: number | null
          finished_at?: number | null
      }
    | {
          type: 'tool_call'
          id: string
          name: string
          input: string
          finished: boolean
      }
    | {
          type: 'tool_result'
          tool_call_id: string
          name: string
          content: string
          metadata: string
          is_error: boolean
      }
    | {
          type: 'code_block'
          id: string
          content: string
          status: string
          outputs?: Array<Record<string, unknown>> | null
          container_id?: string | null
      }

export enum FinishReason {
    END_TURN = 'end_turn',
    MAX_TOKENS = 'max_tokens',
    TOOL_USE = 'tool_use',
    CANCELED = 'canceled',
    ERROR = 'error',
    PERMISSION_DENIED = 'permission_denied',
    PAUSE_TURN = 'pause_turn',
    UNKNOWN = 'unknown'
}

export interface ChatHistoryMessage {
    id: string
    role: 'user' | 'assistant' | 'tool'
    content: ContentPart[] // Direct array of ContentPart objects
    usage: {
        completion_tokens: number
        prompt_tokens: number
        total_tokens: number
        completion_tokens_details: {
            reasoning_tokens: number
        } | null
        prompt_tokens_details: unknown | null
    } | null
    tokens: number | null
    model: string
    created_at: string
    files: {
        id: string
        file_name: string
        file_size: number
        content_type: string
        created_at: string
    }[]
    finish_reason: FinishReason | null
    metadata?: {
        media?: {
            enabled?: boolean
            type?: ChatMediaType
            model_name?: string
            provider?: string
            references?: MediaReference[]
            mini_tools?: {
                id?: string
                name?: string
                reference_file_ids?: string[]
            }
            [key: string]: unknown
        }
        [key: string]: unknown
    }
}

export interface ChatHistoryResponse {
    messages: ChatHistoryMessage[]
    has_more: boolean
    total_count: number
}

/**
 * Extracts text content from a message's content field
 * @param message - The chat message containing content parts
 * @returns The concatenated text content from all text parts
 */
export function extractTextFromMessage(message: ChatHistoryMessage): string {
    return message.content
        .filter(
            (part): part is Extract<ContentPart, { type: 'text' }> =>
                part.type === 'text'
        )
        .map((part) => part.text)
        .join('')
}
