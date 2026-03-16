export interface CreditBalanceResponse {
    user_id: string
    credits: number
    bonus_credits?: number
    updated_at: string
}

export interface CreditUsageSession {
    session_id: string
    session_title: string
    credits: number
    bonus_credits: number
    updated_at: string
}

export interface CreditUsageResponse {
    sessions: CreditUsageSession[]
    total: number
}

export interface SessionUsageItem {
    id: number
    billing_kind: string
    source_domain: string
    model_id: string | null
    tool_name: string | null
    provider: string | null
    input_tokens: number
    output_tokens: number
    cache_read_tokens: number
    cache_write_tokens: number
    reasoning_tokens: number
    cost_usd: number | null
    credits_charged: number
    created_at: string
}

export interface SessionUsageDetailResponse {
    session_id: string
    session_title: string
    items: SessionUsageItem[]
    total_credits: number
    total_items: number
}

export interface LedgerEntry {
    id: number
    entry_type: string
    source_domain: string | null
    source_id: string | null
    delta_credits: number
    delta_bonus_credits: number
    balance_after_credits: number | null
    balance_after_bonus_credits: number | null
    idempotency_key: string | null
    entry_metadata: Record<string, unknown> | null
    created_at: string
}

export interface LedgerHistoryResponse {
    entries: LedgerEntry[]
    total: number
}

export interface ReservationEntry {
    id: string
    session_id: string | null
    source_domain: string
    source_id: string
    billing_kind: string
    quote_strategy: string
    status: string
    model_id: string | null
    tool_name: string | null
    idempotency_key: string | null
    reserved_credits: number
    reserved_bonus_credits: number
    actual_credits: number | null
    actual_bonus_credits: number | null
    released_credits: number | null
    released_bonus_credits: number | null
    quoted_usd: number
    max_usd: number
    actual_usd: number | null
    expires_at: string | null
    created_at: string
    updated_at: string
}

export interface ReservationHistoryResponse {
    entries: ReservationEntry[]
    total: number
}
