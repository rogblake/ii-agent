import { AxiosProgressEvent } from 'axios'

export interface UploadFileRequest {
    session_id?: string
    file: {
        path: string
        content: string
    }
}

export interface UploadFileResponse {
    file: {
        path: string
        url?: string
        size?: number
    }
    success: boolean
    message?: string
}

export interface RemoveFileRequest {
    session_id?: string
    file_path: string
}

export interface UploadMultipleFilesRequest {
    session_id?: string
    files: Array<{
        path: string
        content: string
    }>
}

export interface UploadMultipleFilesResponse {
    results: Array<{
        path: string
        success: boolean
        message?: string
    }>
    totalSuccess: number
    totalFailed: number
}

export interface UploadProgressCallback {
    (progressEvent: AxiosProgressEvent): void
}

export interface UploadFromUrlRequest {
    url: string
    session_id?: string
    file_name?: string
}

export interface GetUploadedFilesResponse {
    files: string[]
}

export interface CheckFileExistsRequest {
    path: string
    session_id?: string
}

export interface CheckFileExistsResponse {
    exists: boolean
}

export interface ValidateFileResponse {
    valid: boolean
    message?: string
}

export interface GenerateUploadUrlRequest {
    filename: string
    content_type: string
    size_bytes?: number
}

export interface GenerateUploadUrlResponse {
    asset_id: string
    upload_url: string
    storage_path: string
}

export interface UploadCompleteRequest {
    session_id?: string
}

export interface UploadCompleteResponse {
    id: string
    filename: string
    content_type: string | null
    size_bytes: number | null
    asset_type: string
    source: string
    upload_status: string
    is_public: boolean
    url: string | null
    created_at: string | null
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
