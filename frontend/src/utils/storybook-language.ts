import type { StorybookLanguage } from '@/typings/agent'

const STORYBOOK_LANGUAGE_BY_LOCALE: Record<string, StorybookLanguage> = {
    en: 'English',
    vi: 'Vietnamese',
    ja: 'Japanese',
    hi: 'Hindi',
    ko: 'Korean'
}

export function getStorybookLanguageFromLocale(
    locale: string
): StorybookLanguage {
    const normalized = locale.toLowerCase().split(/[-_]/)[0] || locale
    return STORYBOOK_LANGUAGE_BY_LOCALE[normalized] ?? 'English'
}
