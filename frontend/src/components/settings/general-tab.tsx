import { useTheme } from 'next-themes'
import { useTranslation } from 'react-i18next'

import {
    Select,
    SelectContent,
    SelectItem,
    SelectTrigger,
    SelectValue
} from '../ui/select'
import { Icon } from '../ui/icon'
import { useAppDispatch, useAppSelector } from '@/state/store'
import { selectUserLanguage, setUser } from '@/state/slice/user'
import { userService } from '@/services/user.service'
import { authService } from '@/services/auth.service'
import { SUPPORTED_LANGUAGES, changeLanguage, type LanguageCode } from '@/i18n'
import { toast } from 'sonner'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

const GeneralTab = () => {
    const { t } = useTranslation()
    const { theme, setTheme } = useTheme()
    const dispatch = useAppDispatch()
    const currentLanguage = useAppSelector(selectUserLanguage)
    const isSage = useIsSageTheme()

    const handleLanguageChange = async (value: string) => {
        try {
            await userService.updateLanguage(value)
            await changeLanguage(value as LanguageCode)
            const userRes = await authService.getCurrentUser()
            dispatch(setUser(userRes))
        } catch {
            toast.error(t('errors.generic'))
        }
    }

    return (
        <div className="divide-y divide-white/30">
            <div className="flex flex-col md:flex-row md:items-center gap-4 justify-between pb-6">
                <div>
                    <h2 className="text-[18px] font-semibold mb-1">
                        {t('settings.general.theme')}
                    </h2>
                    <p className="text-xs max-w-[332px]">
                        {t('settings.general.themeDescription', {
                            appName: isSage ? 'SAGE' : t('common.appName')
                        })}
                    </p>
                </div>
                <Select
                    onValueChange={(value) => {
                        setTheme(value)
                    }}
                    value={theme}
                >
                    <SelectTrigger className="**:fill-black **:dark:fill-white w-[229px]">
                        <div className="flex items-center gap-4">
                            <SelectValue
                                placeholder={t('settings.general.selectTheme')}
                            />
                        </div>
                    </SelectTrigger>
                    <SelectContent>
                        <SelectItem value={'system'}>
                            <div className="flex items-center gap-4">
                                <Icon
                                    name="cpu"
                                    className={`size-6 fill-black`}
                                />
                                {t('settings.general.system')}
                            </div>
                        </SelectItem>
                        <SelectItem value={'dark'}>
                            <div className="flex items-center gap-4">
                                <Icon
                                    name="moon"
                                    className={`size-6 fill-black`}
                                />
                                {t('settings.general.dark')}
                            </div>
                        </SelectItem>
                        <SelectItem value={'light'}>
                            <div className="flex items-center gap-4">
                                <Icon
                                    name="sun"
                                    className={`size-6 stroke-black`}
                                />
                                {t('settings.general.light')}
                            </div>
                        </SelectItem>
                    </SelectContent>
                </Select>
            </div>
            <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 py-6">
                <div>
                    <h2 className="text-[18px] font-semibold mb-1">
                        {t('settings.general.language')}
                    </h2>
                    <p className="text-xs max-w-[332px]">
                        {t('settings.general.languageDescription', {
                            appName: isSage ? 'SAGE' : t('common.appName')
                        })}
                    </p>
                </div>
                <Select
                    onValueChange={handleLanguageChange}
                    value={currentLanguage}
                >
                    <SelectTrigger className="**:fill-black **:dark:fill-white w-[229px]">
                        <div className="flex items-center gap-4">
                            <SelectValue
                                placeholder={t(
                                    'settings.general.selectLanguage'
                                )}
                            />
                        </div>
                    </SelectTrigger>
                    <SelectContent>
                        {SUPPORTED_LANGUAGES.map((lang) => (
                            <SelectItem key={lang.code} value={lang.code}>
                                <div className="flex items-center gap-4">
                                    <span
                                        className="text-xl leading-none"
                                        aria-hidden="true"
                                    >
                                        {lang.flag}
                                    </span>
                                    {lang.nativeName}
                                </div>
                            </SelectItem>
                        ))}
                    </SelectContent>
                </Select>
            </div>
        </div>
    )
}

export default GeneralTab
