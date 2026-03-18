import type { MediaReference } from './chat'
import type { ChatMediaType } from '@/constants/media-type-config'
import type {
    ImageAspectRatio,
    ImageResolution,
    PageCount,
    TextPosition,
    StorybookLanguage,
    StorybookGenre
} from './media-types'

export enum TAB {
    CODE = 'code',
    TERMINAL = 'terminal',
    RESULT = 'result',
    BUILD = 'build',
    PROJECT = 'project'
}

export enum VIEW_MODE {
    CHAT = 'chat',
    DESIGN = 'design'
}

export enum QUESTION_MODE {
    AGENT = 'agent',
    CHAT = 'chat'
}

export enum BUILD_MODE {
    BUILD = 'build',
    DESIGN = 'design',
    PLAN = 'plan',
    HELP = 'help'
}

export const AVAILABLE_MODELS = [
    'claude-sonnet-4@20250514',
    'claude-opus-4@20250514',
    'claude-3-7-sonnet@20250219',
    'gemini-2.5-pro-preview-05-06',
    'gpt-4.1'
]

export enum WebSocketConnectionState {
    CONNECTING = 'connecting',
    CONNECTED = 'connected',
    DISCONNECTED = 'disconnected'
}

export enum RunStatus {
    PENDING = 'pending',
    RUNNING = 'running',
    COMPLETED = 'completed',
    PAUSED = 'paused',
    ABORTING = 'aborting',
    ABORTED = 'aborted',
    FAILED = 'failed',
    ERROR = 'error',
    SYSTEM_INTERRUPTED = 'system_interrupted'
}

const TERMINAL_STATUSES: ReadonlySet<string> = new Set([
    RunStatus.COMPLETED,
    RunStatus.FAILED,
    RunStatus.ERROR,
    RunStatus.ABORTED,
    RunStatus.SYSTEM_INTERRUPTED
])

export function isTerminalRunStatus(status: string): boolean {
    return TERMINAL_STATUSES.has(status)
}

export type Source = {
    title: string
    url: string
}

export enum AgentEvent {
    AGENT_INITIALIZED = 'agent_initialized',
    USER_MESSAGE = 'user_message',
    CONNECTION_ESTABLISHED = 'connection_established',
    WORKSPACE_INFO = 'workspace_info',
    PROCESSING = 'processing',
    AGENT_THINKING_START = 'agent_thinking_start',
    AGENT_THINKING = 'agent_thinking',
    AGENT_THINKING_DELTA = 'agent_thinking_delta',
    TOOL_CALL = 'tool_call',
    TOOL_RESULT = 'tool_result',
    TOOL_CONFIRMATION = 'tool_confirmation',
    AGENT_RESPONSE = 'agent_response',
    AGENT_RESPONSE_DELTA = 'agent_response_delta',
    COMPLETE = 'complete',
    ERROR = 'error',
    SYSTEM = 'system',
    PONG = 'pong',
    UPLOAD_SUCCESS = 'upload_success',
    BROWSER_USE = 'browser_use',
    FILE_EDIT = 'file_edit',
    AGENT_RESPONSE_INTERRUPTED = 'agent_response_interrupted',
    AGENT_CONTINUE = 'agent_continue',
    STATUS_UPDATE = 'status_update',
    SANDBOX_STATUS = 'sandbox_status',
    SUB_AGENT_COMPLETE = 'sub_agent_complete',
    MODEL_COMPACT = 'model_compact',
    PLAN_GENERATED = 'plan_generated',
    MILESTONE_UPDATE = 'milestone_update',
    PLAN_MODIFICATION_OPTIONS = 'plan_modification_options',
    WAITING_FOR_USER_INPUT = 'waiting_for_user_input',
    TESTFLIGHT_LOG = 'testflight_log',
    // Apple authentication events
    APPLE_AUTH_STATUS = 'apple_auth_status',
    APPLE_2FA_REQUIRED = 'apple_2fa_required',
    APPLE_TEAM_SELECTION = 'apple_team_selection',
    APPLE_APP_SETUP_STATUS = 'apple_app_setup_status',
    APPLE_APPS_LIST = 'apple_apps_list',
    APPLE_AUTH_CHECK_RESULT = 'apple_auth_check_result',
    EXPO_TOKEN_SAVED = 'expo_token_saved'
}

export enum TOOL {
    SEQUENTIAL_THINKING = 'sequential_thinking',
    MESSAGE_USER = 'message_user',
    SEND_USER_FILES = 'send_user_files',
    BROWSER_USE = 'browser_use',
    PRESENTATION = 'presentation',
    WEB_SEARCH = 'web_search',
    WEB_BATCH_SEARCH = 'web_batch_search',
    IMAGE_SEARCH = 'image_search',
    VISIT = 'web_visit',
    VISIT_COMPRESS = 'web_visit_compress',
    SHELL_EXEC = 'shell_exec',
    SHELL_KILL_PROCESS = 'shell_kill_process',
    SHELL_VIEW = 'shell_view',
    SHELL_WRITE_TO_PROCESS = 'shell_write_to_process',
    SHELL_WAIT = 'shell_wait',
    FULLSTACK_PROJECT_INIT = 'fullstack_project_init',
    RESTART_FULLSTACK_SERVERS = 'restart_fullstack_servers',
    GET_SERVER_STATUS = 'get_server_status',
    SAVE_CHECKPOINT = 'save_checkpoint',
    COMPLETE = 'complete',
    STATIC_DEPLOY = 'static_deploy',
    REGISTER_DEPLOYMENT = 'register_deployment',
    PDF_TEXT_EXTRACT = 'pdf_text_extract',
    AUDIO_TRANSCRIBE = 'audio_transcribe',
    GENERATE_AUDIO_RESPONSE = 'generate_audio_response',
    VIDEO_GENERATE = 'generate_video',
    CONCATENATE_VIDEOS = 'concatenate_videos',
    EXTRACT_FRAMES = 'extract_frames',
    // Legacy - kept for backward compatibility with stored data
    LONG_VIDEO_GENERATE = 'generate_long_video_from_text',
    LONG_VIDEO_GENERATE_FROM_IMAGE = 'generate_long_video_from_image',
    IMAGE_GENERATE = 'generate_image',
    DEEP_RESEARCH = 'deep_research',
    LIST_HTML_LINKS = 'list_html_links',
    RETURN_CONTROL_TO_USER = 'return_control_to_user',
    SLIDE_DECK_INIT = 'slide_deck_init',
    SLIDE_DECK_COMPLETE = 'slide_deck_complete',
    DISPLAY_IMAGE = 'display_image',
    REVIEWER_AGENT = 'reviewer_agent',
    A2A_AGENT = 'a2a_agent',
    SUB_AGENT = 'sub_agent',
    SUB_AGENT_RESEARCHER = 'sub_agent_researcher',
    DESIGN_DOCUMENT_AGENT = 'design_document_agent',
    SUBMIT_PLAN = 'submit_plan',
    SUBMIT_PLAN_MODIFICATION_SUGGESTIONS = 'submit_plan_modification_suggestions',

    GET_DATABASE_CONNECTION = 'get_database_connection',
    GET_OPENAI_KEY = 'get_openai_api_key',
    // Legacy browser action event types retained for historical session playback
    BROWSER_CLICK = 'browser_click',
    BROWSER_CLOSE = 'browser_close',
    BROWSER_CONSOLE_MESSAGES = 'browser_console_messages',
    BROWSER_DRAG = 'browser_drag',
    BROWSER_EVALUATE = 'browser_evaluate',
    BROWSER_HANDLE_DIALOG = 'browser_handle_dialog',
    BROWSER_HOVER = 'browser_hover',
    BROWSER_NAVIGATE = 'browser_navigate',
    BROWSER_NETWORK_REQUESTS = 'browser_network_requests',
    BROWSER_PRESS_KEY = 'browser_press_key',
    BROWSER_SELECT_OPTION = 'browser_select_option',
    BROWSER_SNAPSHOT = 'browser_snapshot',
    BROWSER_TAKE_SCREENSHOT = 'browser_take_screenshot',
    BROWSER_TYPE = 'browser_type',
    BROWSER_WAIT_FOR = 'browser_wait_for',
    BROWSER_TAB_CLOSE = 'browser_tab_close',
    BROWSER_TAB_LIST = 'browser_tab_list',
    BROWSER_TAB_NEW = 'browser_tab_new',
    BROWSER_TAB_SELECT = 'browser_tab_select',
    BROWSER_MOUSE_CLICK_XY = 'browser_mouse_click_xy',
    BROWSER_MOUSE_DRAG_XY = 'browser_mouse_drag_xy',
    BROWSER_MOUSE_MOVE_XY = 'browser_mouse_move_xy',
    BROWSER_NAVIGATION = 'browser_navigation',
    BROWSER_WAIT = 'browser_wait',
    BROWSER_VIEW_INTERACTIVE_ELEMENTS = 'browser_view_interactive_elements',
    BROWSER_SCROLL_DOWN = 'browser_scroll_down',
    BROWSER_SCROLL_UP = 'browser_scroll_up',
    BROWSER_SWITCH_TAB = 'browser_switch_tab',
    BROWSER_OPEN_NEW_TAB = 'browser_open_new_tab',
    BROWSER_GET_SELECT_OPTIONS = 'browser_get_select_options',
    BROWSER_SELECT_DROPDOWN_OPTION = 'browser_select_dropdown_option',
    BROWSER_RESTART = 'browser_restart',
    BROWSER_ENTER_TEXT = 'browser_enter_text',
    BROWSER_ENTER_MULTI_TEXTS = 'browser_enter_multi_texts',

    TODO_WRITE = 'TodoWrite',
    TODO_READ = 'TodoRead',
    READ = 'Read',
    WRITE = 'Write',
    EDIT = 'Edit',
    LS = 'LS',
    BASH = 'Bash',
    BASH_INIT = 'BashInit',
    BASH_VIEW = 'BashView',
    BASH_STOP = 'BashStop',
    BASH_KILL = 'BashKill',
    BASH_LIST = 'BashList',
    BASH_WRITE_TO_PROCESS = 'BashWriteToProcess',
    GLOB = 'Glob',
    GREP = 'ASTGrep',
    MULTI_EDIT = 'MultiEdit',
    REGISTER_PORT = 'register_port',
    MCP_TOOL = 'mcp_tool',
    TASK = 'Task',
    SLIDE_WRITE = 'SlideWrite',
    SLIDE_EDIT = 'SlideEdit',
    SLIDE_GENERATE = 'SlideGenerate',
    READ_REMOTE_IMAGE = 'read_remote_image',
    CODEX_AGENT = 'codex_agent',
    CODEX_EXECUTE = 'codex_execute', // Legacy, kept for backward compatibility
    CODEX_REVIEW = 'codex_review', // Legacy, kept for backward compatibility
    MCP_CODEX_EXECUTE = 'mcp_codex_execute', // New MCP stdio version
    CODEX_MCP_CODEX_EXECUTE = 'mcp_codex-as-mcp_codex_execute', // New MCP stdio version
    MCP_CODEX_REVIEW = 'mcp_codex_review', // New MCP stdio version
    CODEX_MCP_CODEX_REVIEW = 'mcp_codex-as-mcp_codex_review', // New MCP stdio version
    APPLY_PATCH = 'apply_patch',
    SLIDE_APPLY_PATCH = 'slide_apply_patch',
    STR_REPLACE_BASED_EDIT = 'str_replace_based_edit_tool',
    CLAUDE_CODE = 'mcp_claude_code',
    GITHUB = 'github',
    ADD_WEBDEV_SECRETS = 'add_webdev_secrets',
    STRIPE_WEBHOOK_REGISTER = 'stripe_webhook_register',
    ASK_USER_ENV = 'ask_user_env',
    ASK_USER_SELECT = 'ask_user_select',
    SKILL = 'Skill',
    MOBILE_APP_INIT = 'mobile_app_init',
    RESTART_MOBILE_SERVER = 'restart_mobile_server'
}

export type Plan = {
    id: string
    content: string
    status: 'pending' | 'in_progress' | 'completed'
}

export type Milestone = {
    id: string
    content: string
    status: 'pending' | 'in_progress' | 'completed'
    details?: string
    dependencies?: string[]
}

export type PlanModificationSuggestion = {
    id: string
    label: string
    description: string
    prompt_template: string
}

export interface FileURLContent {
    type: 'file_url'
    url: string
    mime_type: string
    name: string
    size: number
}

export interface AgentContext {
    agentId: string
    agentType: 'main' | 'subagent'
    agentName?: string
    parentAgentId?: string
    nestingLevel: number
    startTime?: number
    endTime?: number
    status?: 'running' | 'completed' | 'failed'
}

export type ActionStep = {
    type: TOOL
    data: {
        isResult?: boolean
        tool_call_id?: string
        tool_name?: string
        tool_display_name?: string
        tool_logo?: string
        agentContext?: AgentContext
        tool_input?: {
            message?: string
            description?: string
            action?: string
            text?: string
            thought?: string
            path?: string
            repo?: string
            file_text?: string
            file_path?: string
            command?: string
            url?: string
            query?: string
            queries?: string[]
            file?: string
            instruction?: string
            output_filename?: string
            output_path?: string
            key?: string
            session_id?: string
            seconds?: number
            input?: string
            enter?: boolean
            framework?: string
            project_name?: string
            database_type?: string
            context?: unknown
            metadata?: Record<string, unknown>
            agent_name?: string
            agent_url?: string
            agent?: unknown
            agent_info?: unknown
            old_string?: string
            new_string?: string
            old_str?: string
            new_str?: string
            project_directory?: string
            commit_message?: string
            todos?: Plan[]
            session_names?: string[]
            session_name?: string
            press_enter?: boolean
            content?: string
            pattern?: string
            include?: string
            name?: string
            tool_name?: string
            prompt?: string
            port?: number
            element?: string
            x?: number
            y?: number
            filename?: string
            presentation_name?: string
            slide_number?: number
            enter_texts?: Array<{
                text: string
                coordinate_x: number
                coordinate_y: number
                press_enter?: boolean
            }>
            coordinate_x_start?: number
            coordinate_y_start?: number
            coordinate_x_end?: number
            coordinate_y_end?: number
            urls?: string[]
            changes?: Record<
                string,
                {
                    add: {
                        content: string
                    }
                    delete: {
                        content: string
                    }
                    update: {
                        unified_diff: string
                    }
                }
            >
            endpoint_url?: string
            secrets?: Array<{ key: string; value: string }>
            attachments?: string[]
            skill?: string
        }
        result?:
            | string
            | Record<string, unknown>
            | Record<string, unknown>[]
            | FileURLContent
        query?: string
        content?: string
        path?: string
    }
}

export interface ToolConfirmationRequirement {
    id: string
    needs_confirmation: boolean
    needs_user_input: boolean
    needs_external_execution: boolean
    tool_execution?: {
        tool_call_id: string
        tool_name: string
        tool_args: Record<string, unknown>
    }
    user_input_schema?: Array<{
        name: string
        field_type: string
        description?: string
        value?: unknown
    }>
}

export interface ToolConfirmationData {
    run_id: string
    session_id: string
    message: string
    active_requirements: ToolConfirmationRequirement[]
}

export interface Message {
    id: string
    role: 'user' | 'assistant' | 'system'
    content?: string
    timestamp: number
    action?: ActionStep
    files?: Array<{
        id: string
        file_name: string
        file_size: number
        content_type: string
        created_at: string
    }>
    fileContents?: { [filename: string]: string } // Base64 content of files
    attachments?: Array<AttachmentMeta>
    isHidden?: boolean
    isThinkMessage?: boolean
    agentContext?: AgentContext
    subagentMessages?: Message[] // For grouping subagent messages
    toolConfirmation?: ToolConfirmationData
    videoFrames?: VideoFrameReference[] // Video frames attached to the message (for video generation)
}

export type AttachmentType = 'code' | 'xlsx' | 'documents' | 'archive'

export interface AttachmentMeta {
    name: string
    url: string
    file_type: AttachmentType
}

export interface ForkInfo {
    fork_type: string
    parent_session_id: string
    context: {
        attachments: string[]
        additional_instruction?: string | null
    }
    forked_at: string
}

export interface ISession {
    id: string
    workspace_dir: string
    created_at: string
    updated_at?: string
    name?: string
    title_pending?: boolean
    status?: string
    sandbox_id?: string | null
    agent_type?: string
    is_public?: boolean
    public_url?: string | null
    project_id?: string | null
    last_message_at?: string | null
    parent_session_id?: string | null
    llm_setting_id?: string | null
    metadata?: {
        media?: ChatMediaPreference
        fork_info?: ForkInfo
        [key: string]: unknown
    }
}

export interface IEvent {
    id: string
    type: AgentEvent
    content: Record<string, unknown>
    timestamp: string
    workspace_dir: string
    run_id?: string
    session_id?: string
}

export interface ToolSettings {
    task_agent: boolean
    deep_research: boolean
    pdf: boolean
    media_generation: boolean
    audio_generation: boolean
    thinking_tokens: number
    enable_reviewer: boolean
    design_document: boolean
    codex_tools: boolean
    claude_code: boolean
}

export type {
    ImageAspectRatio,
    ImageResolution,
    PageCount,
    TextPosition,
    StorybookLanguage,
    StorybookGenre
}

// Video-specific types
export type VideoDuration =
    | '4s'
    | '6s'
    | '8s'
    | '10s'
    | '12s'
    | '18s'
    | '24s'
    | '30s'
export type VideoResolution = '720p' | '1080p'
export type VideoAspectRatio = '16:9' | '9:16'

export interface VideoSettings {
    duration: VideoDuration
    resolution: VideoResolution
    aspect_ratio: VideoAspectRatio
    audio_included: boolean
    multishot_mode: boolean
}

export interface VideoFrameReference {
    id: string
    url: string
    type: 'start' | 'end'
    file_id?: string
}

export interface StorybookContext {
    storybook_id: string
    reference_images: string[]
    scripts: string[]
}

export interface ChatMediaPreference {
    enabled: boolean
    type: ChatMediaType
    model_name: string
    provider: string
    mini_tools?: ChatMediaToolSelection
    template_id?: string
    template_name?: string
    template_prompt?: string
    aspect_ratio?: ImageAspectRatio
    resolution?: ImageResolution
    page_count?: PageCount
    text_position?: TextPosition
    language?: StorybookLanguage
    language_source?: 'system' | 'user'
    genre?: StorybookGenre
    manga_layout?: boolean
    rich_dialogue?: boolean
    voice_enabled?: boolean
    references?: MediaReference[]
    advanced_mode?: boolean
    // Video-specific settings
    video_settings?: VideoSettings
    video_frames?: VideoFrameReference[]
    // Storybook context for video generation (auto-detected when switching modes)
    storybook_context?: StorybookContext
}
export interface ChatMediaToolSelection {
    id: string
    name: string
    reference_file_ids?: string[]
}
export interface ChatToolSettings {
    web_search: boolean
    web_visit: boolean
    image_search: boolean
    code_interpreter: boolean
    generate_image?: boolean
    generate_video?: boolean
}
export interface GooglePickerResponse {
    action: string
    docs?: Array<GoogleDocument>
}

export interface GoogleDocument {
    id: string
    name: string
    thumbnailUrl: string
    mimeType: string
}

export interface LLMConfig {
    api_key?: string
    model?: string
    base_url?: string
    max_retries?: string
    temperature?: string
    vertex_region?: string
    vertex_project_id?: string
    api_type?: string
    cot_model?: boolean
    azure_endpoint?: string
    azure_api_version?: string
}

export interface ISetting {
    llm_configs?: {
        [provider: string]: LLMConfig
    }
    search_config?: {
        firecrawl_api_key?: string
        firecrawl_base_url?: string
        serpapi_api_key?: string
        tavily_api_key?: string
        jina_api_key?: string
    }
    media_config?: {
        gcp_project_id?: string
        gcp_location?: string
        gcs_output_bucket?: string
        google_ai_studio_api_key?: string
    }
    audio_config?: {
        openai_api_key: string
        azure_endpoint: string
        azure_api_version: string
    }
    third_party_integration_config?: {
        neon_db_api_key: string
        openai_api_key: string
        vercel_api_key: string
    }
    sandbox_config?: {
        mode: string
        template_id: string
        sandbox_api_key: string
    }
}

export enum BUILD_STEP {
    THINKING = 'thinking',
    PLAN = 'plan',
    BUILD = 'build'
}

export interface IMCPTool {
    name: string
    author: string
    description: string
    logo: string
    url: string
    config: Record<string, unknown>
    isRequireKey?: boolean
}

export enum AGENT_TYPE {
    GENERAL = 'general',
    MEDIA = 'media',
    SLIDE = 'slide',
    SLIDE_NANO_BANANA = 'slide_nano_banana',
    WEBSITE_BUILD = 'website_build',
    CODEX = 'codex',
    CLAUDE_CODE = 'claude_code',
    DEEP_RESEARCH = 'deep_research',
    FAST_RESEARCH = 'fast_research',
    RESEARCH_TO_WEBSITE = 'research_to_website',
    MOBILE_APP = 'mobile_app'
}

export interface PresentationListResponse {
    session_id?: string
    presentations?: {
        name?: string
        slide_count?: number
        last_updated?: string
        slides?: {
            id: string
            presentation_name?: string
            slide_number?: number
            slide_title?: string
            slide_content?: string
            session_id?: string
            metadata?: Record<string, unknown>
            created_at?: string
            updated_at?: string
        }[]
    }[]
    total?: number
}

export interface UpdateSlideRequest {
    session_id: string
    presentation_name: string
    slide_number: number
    content: string
    title: string
    description?: string
}

export interface UpdateSlideResponse {
    success: boolean
    error?: string
    error_code?: string
}
