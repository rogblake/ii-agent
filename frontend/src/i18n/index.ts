import i18n from 'i18next'
import { initReactI18next } from 'react-i18next'

import en from './locales/en.json'
import vi from './locales/vi.json'
import hi from './locales/hi.json'
import ja from './locales/ja.json'

export const SUPPORTED_LANGUAGES = [
    { code: 'en', name: 'English', nativeName: 'English', flag: '🇺🇸' },
    { code: 'vi', name: 'Vietnamese', nativeName: 'Tiếng Việt', flag: '🇻🇳' },
    { code: 'hi', name: 'Hindi', nativeName: 'हिन्दी', flag: '🇮🇳' },
    { code: 'ja', name: 'Japanese', nativeName: '日本語', flag: '🇯🇵' }
] as const

export type LanguageCode = (typeof SUPPORTED_LANGUAGES)[number]['code']

export const DEFAULT_LANGUAGE: LanguageCode = 'en'

const resources = {
    en: { translation: en },
    vi: { translation: vi },
    hi: { translation: hi },
    ja: { translation: ja }
}

i18n.use(initReactI18next).init({
    resources,
    lng: localStorage.getItem('language') || DEFAULT_LANGUAGE,
    fallbackLng: DEFAULT_LANGUAGE,
    interpolation: {
        escapeValue: false
    },
    react: {
        useSuspense: true
    }
})

export const changeLanguage = (language: LanguageCode) => {
    localStorage.setItem('language', language)
    return i18n.changeLanguage(language)
}

export default i18n
