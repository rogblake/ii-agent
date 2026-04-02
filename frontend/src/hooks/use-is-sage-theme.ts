export function useIsSageTheme() {
    return import.meta.env.VITE_THEME?.toLowerCase() === 'sage'
}
