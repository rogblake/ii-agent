/**
 * Design Mode Components
 *
 * A visual editing system for modifying element styles in the preview iframe.
 */

export { DesignModeWrapper } from './design-mode-wrapper'
export { SlideDesignModeView } from './slide/slide-design-mode-view'
export { NanoBananaDesignModeView } from './nano-banana'
export { InspectorSidebar } from './inspector-sidebar'
export { AIChatModal } from './ai-chat-modal'
export { DesignPanel } from './design-panel'
export { useDesignMode } from './use-design-mode'
export {
    DesignModeProvider,
    useDesignModeContext,
    useOptionalDesignModeContext
} from './design-mode-context'
export type {
    ElementInfo,
    DesignChange,
    DesignModeState,
    DesignModeMessage,
    DesignModeMessageType
} from './types'
export type { AIChangeResult } from './ai-chat-modal'
