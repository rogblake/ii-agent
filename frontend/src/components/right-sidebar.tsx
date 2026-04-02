import { useTheme } from 'next-themes'

import { Icon } from './ui/icon'
import { useAppSelector } from '@/state/store'
import { selectUser } from '@/state/slice/user'
import UserProfileDropdown from './user-profile-dropdown'

const RightSidebar = () => {
    const { theme, setTheme } = useTheme()

    const user = useAppSelector(selectUser)

    const toggleTheme = () => {
        setTheme(theme === 'dark' ? 'light' : 'dark')
    }

    if (!user) return null

    return (
        <div className="hidden md:flex items-center justify-between flex-col h-full py-8 px-6 border-l border-grey-2 dark:border-sidebar-border bg-sidebar-bg/30 dark:bg-transparent">
            <div className="flex flex-col items-center gap-4">
                <UserProfileDropdown />

                <div
                    className="size-7 flex items-center justify-center bg-sky-blue-3 dark:bg-sky-blue-3 rounded-full cursor-pointer"
                    onClick={toggleTheme}
                >
                    <Icon
                        name={theme === 'dark' ? 'sun' : 'moon'}
                        className="size-[18px] fill-none text-black stroke-black dark:stroke-black"
                    />
                </div>
            </div>
        </div>
    )
}

export default RightSidebar
