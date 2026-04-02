/**
 * TypeScript interfaces for Nano Banana design mode.
 */

// ============ Detection Types ============

export interface BoundingBox {
    x: number // Left edge as % of image width (0-100)
    y: number // Top edge as % of image height (0-100)
    width: number // Width as % of image width (0-100)
    height: number // Height as % of image height (0-100)
}

export interface ComponentStyles {
    font_size?: string
    font_weight?: string
    color?: string
    background_color?: string
    text_align?: string
}

export interface DetectedComponent {
    design_id: string
    component_type: string
    label: string
    text_content: string | null
    bounding_box: BoundingBox
    z_index: number
    confidence: number
    styles?: ComponentStyles | null
}

// ============ Selection Types ============

export type SelectionType = 'component' | 'spot' | 'box'

export interface Selection {
    type: SelectionType

    // For component selection
    component_id?: string // design_id of selected component

    // For spot selection (single point)
    spot_x?: number // X as % of image width (0-100)
    spot_y?: number // Y as % of image height (0-100)

    // For box selection (rectangular region)
    box?: BoundingBox
}

// ============ Instruction Types ============

export type InstructionType = 'text_edit' | 'ai_modify' | 'remove_background'

export interface Instruction {
    id: string
    selection: Selection
    instruction_type: InstructionType

    // For text_edit
    new_text?: string

    // For ai_modify
    ai_prompt?: string

    timestamp: number
}

// ============ State Types ============

export type DetectionStatus = 'idle' | 'loading' | 'ready' | 'error'

export interface SlideDetectionState {
    slideNumber: number
    imageUrl: string
    status: DetectionStatus
    components: DetectedComponent[]
    overlayHtml: string | null
    imageWidth: number
    imageHeight: number
    error: string | null
}

export interface NanoBananaSlideInfo {
    slideNumber: number
    imageUrl: string
}

// ============ Version Types ============

export interface SlideVersionInfo {
    id: string
    version: number
    image_url: string
    thumbnail_url?: string
    edit_summary?: string
    created_at: string
    is_current: boolean
}

// ============ Selection Mode ============

export type SelectionMode = 'component' | 'spot' | 'box'
