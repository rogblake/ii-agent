import { motion } from 'framer-motion'
import { Shimmer } from './ai-elements/shimmer'
import { useTranslation } from 'react-i18next'
import { useIsSageTheme } from '@/hooks/use-is-sage-theme'

const ThinkingMessage = () => {
    const { t } = useTranslation()
    const isSage = useIsSageTheme()
    const appName = isSage ? 'SAGE' : t('common.appName')

    return (
        <div className="flex items-center gap-x-1.5 text-black/[0.56] dark:text-[#999999] text-sm">
            <Shimmer as="span" duration={2} className="inline">
                {t('chat.thinkingStatus', { appName })}
            </Shimmer>
            <div className="flex gap-x-1">
                <motion.div
                    className="size-1 bg-[#999999] rounded-full"
                    animate={{
                        y: [0, -6, 0],
                        opacity: [0.3, 1, 0.3]
                    }}
                    transition={{
                        duration: 1.2,
                        repeat: Infinity,
                        delay: 0,
                        ease: 'easeInOut'
                    }}
                />
                <motion.div
                    className="size-1 bg-[#999999] rounded-full"
                    animate={{
                        y: [0, -6, 0],
                        opacity: [0.3, 1, 0.3]
                    }}
                    transition={{
                        duration: 1.2,
                        repeat: Infinity,
                        delay: 0.15,
                        ease: 'easeInOut'
                    }}
                />
                <motion.div
                    className="size-1 bg-[#999999] rounded-full"
                    animate={{
                        y: [0, -6, 0],
                        opacity: [0.3, 1, 0.3]
                    }}
                    transition={{
                        duration: 1.2,
                        repeat: Infinity,
                        delay: 0.3,
                        ease: 'easeInOut'
                    }}
                />
            </div>
        </div>
    )
}

export default ThinkingMessage
