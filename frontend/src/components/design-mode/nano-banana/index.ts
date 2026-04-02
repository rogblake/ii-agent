/**
 * Nano Banana Design Mode Components
 *
 * This module provides components for editing image-based (nano banana) slides
 * through vision-based component detection and AI-powered regeneration.
 */

// Main view component
export { NanoBananaDesignModeView } from './nano-banana-design-mode-view'

// Sub-components
export { NanoBananaToolbar } from './nano-banana-toolbar'
export { NanoBananaSlidePanel } from './nano-banana-slide-panel'
export { NanoBananaInspector } from './nano-banana-inspector'
export { NanoBananaVersionSelector } from './nano-banana-version-selector'
export { SelectionOverlay } from './selection-overlay'

// Hooks
export { useNanoBananaDetection } from './use-nano-banana-detection'
export { useNanoBananaSelection } from './use-nano-banana-selection'
export { useNanoBananaInstructions } from './use-nano-banana-instructions'
export { useNanoBananaVersions } from './use-nano-banana-versions'

// Types
export type {
    BoundingBox,
    ComponentStyles,
    DetectedComponent,
    SelectionType,
    Selection,
    InstructionType,
    Instruction,
    DetectionStatus,
    SlideDetectionState,
    NanoBananaSlideInfo,
    SlideVersionInfo,
    SelectionMode
} from './types'
