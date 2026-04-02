import { Icon } from '../ui/icon'
import { Button } from '../ui/button'
import { useTranslation } from 'react-i18next'

interface AwakeMeUpScreenProps {
    isLoading: boolean
    onAwakeClick: () => void
}

const AwakeMeUpScreen = ({ isLoading, onAwakeClick }: AwakeMeUpScreenProps) => {
    const { t } = useTranslation()
    return (
        <div className="w-full h-full flex-1 flex items-center justify-center bg-white dark:bg-charcoal">
            <div className="flex flex-col items-center gap-6">
                <Icon name="sleep" className="fill-black dark:fill-white" />
                <div className="text-center dark:text-sky-blue-2">
                    <h2 className="text-[24px] md:text-[32px] font-semibold mb-1">
                        {t('agent.awake.sleeping')}
                    </h2>
                    <p className="text-lg md:text-2xl">
                        {t('agent.awake.toSavePower')}
                    </p>
                </div>
                <Button
                    onClick={onAwakeClick}
                    className="bg-firefly h-10 md:h-12 text-sky-blue-2 dark:bg-sky-blue dark:text-black font-semibold w-full max-w-[247px]"
                >
                    {isLoading && (
                        <Icon
                            name="loading"
                            className="animate-spin size-6 fill-black"
                        />
                    )}
                    {t('agent.awake.wakeMeUp')}
                </Button>
            </div>
        </div>
    )
}

export default AwakeMeUpScreen
