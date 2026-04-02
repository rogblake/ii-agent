export type MiniToolId = string

export type MiniTool = {
    id: MiniToolId
    name: string
    preview?: string
    /** Minimum number of images required (default: 1) */
    min_images?: number
    /** Maximum number of images allowed (default: 1) */
    max_images?: number
}
