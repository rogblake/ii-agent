export interface GenerateUploadUrlRequest {
    file_name: string
    content_type: string
    file_size: number
}

export interface GenerateUploadUrlResponse {
    id: string
    upload_url: string
}

export interface UploadCompleteRequest {
    id: string
    file_name: string
    file_size: number
    content_type: string
    session_id?: string
}

export interface UploadCompleteResponse {
    file_url: string
}

export type MediaLibrarySource = 'upload' | 'generated'

export interface MediaLibraryItem {
    id: string
    name: string
    url: string
    source: MediaLibrarySource
    created_at: string
}

export interface MediaLibraryResponse {
    items: MediaLibraryItem[]
    total: number
    limit: number
    offset: number
    has_more: boolean
}
