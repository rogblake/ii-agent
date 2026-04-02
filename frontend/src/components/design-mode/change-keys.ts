import type { DesignChange } from './types'

type ChangeKeyParts = Pick<
    DesignChange,
    'designId' | 'type' | 'property' | 'slideNumber'
>

export function normalizeSlideNumber(
    value: DesignChange['slideNumber']
): number | null {
    return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export function buildDesignChangeKey(change: ChangeKeyParts): string {
    const slideNumber = normalizeSlideNumber(change.slideNumber)
    const slidePrefix = slideNumber === null ? '' : `${slideNumber}:`
    return `${slidePrefix}${change.designId}:${change.type}:${change.property}`
}

export function buildDesignChangeKeyWithTimestamp(
    change: ChangeKeyParts & Pick<DesignChange, 'timestamp'>
): string {
    return `${buildDesignChangeKey(change)}:${change.timestamp}`
}
