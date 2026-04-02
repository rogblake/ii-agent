import { useTheme } from 'next-themes'
import { Icon } from './ui/icon'

const SwitchLanguage = () => {
    const { theme, setTheme } = useTheme()

    const toggleTheme = () => {
        setTheme(theme === 'dark' ? 'light' : 'dark')
    }

    return (
        <button
            className="flex items-center justify-center cursor-pointer"
            onClick={toggleTheme}
        >
            <Icon
                name={theme === 'dark' ? 'sun' : 'moon'}
                className="size-6 text-black dark:text-white"
            />
        </button>
    )
}

export default SwitchLanguage
