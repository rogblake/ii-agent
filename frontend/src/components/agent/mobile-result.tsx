import { useEffect, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import QRCode from 'react-qr-code'
import { Icon } from '../ui/icon'
import dayjs from 'dayjs'
import { useIsMobile } from '@/hooks/use-mobile'

interface MobileResultProps {
    resultUrl: string
    mobileAppUrl: string
    refreshKey?: number
    className?: string
}

const MobileResult = ({
    resultUrl,
    mobileAppUrl,
    refreshKey,
    className
}: MobileResultProps) => {
    const { t } = useTranslation()
    const isMobile = useIsMobile()
    const [iframeKey, setIframeKey] = useState(0)

    useEffect(() => {
        if (refreshKey) {
            setIframeKey((prev) => prev + 1)
        }
    }, [refreshKey])

    const handleRefresh = () => {
        setIframeKey((prev) => prev + 1)
    }

    const EXPO_GO_DOWNLOAD_URL = 'https://expo.dev/go'

    // Memoize the QR code URL to prevent re-renders
    // Show Expo Go download link when mobileAppUrl is not available
    const qrCodeUrl = useMemo(
        () => mobileAppUrl || EXPO_GO_DOWNLOAD_URL,
        [mobileAppUrl]
    )

    const isExpoGoQR = !mobileAppUrl

    const mobileAppView = resultUrl ? (
        <iframe
            key={iframeKey}
            src={resultUrl}
            className="absolute top-[44px] left-0 right-0 bottom-6 w-full border-0 bg-white"
            style={{
                height: isMobile ? 'calc(100% - 12px)' : 'calc(100% - 44px)',
                top: isMobile ? '12px' : '44px'
            }}
            title="Mobile App Preview"
            allow="geolocation; camera; microphone"
        />
    ) : (
        <div
            className="absolute top-[44px] left-0 right-0 bottom-6 w-full flex items-center justify-center bg-white"
            style={{ height: 'calc(100% - 44px)' }}
        >
            <div className="flex flex-col items-center gap-3">
                <div className="animate-spin rounded-full h-8 w-8 border-3 border-gray-300 border-t-black" />
                <span className="text-xs text-gray-500">
                    {t('common.loading')}
                </span>
            </div>
        </div>
    )

    if (isMobile) {
        return mobileAppView
    }

    return (
        <div
            className={`flex items-center justify-center w-full h-full bg-white dark:bg-charcoal gap-16 p-8 ${className}`}
        >
            {/* iPhone Frame - Modern iPhone Pro design */}
            <div className="relative flex-shrink-0">
                {/* iPhone outer titanium frame */}
                <div
                    className="relative w-[390px] aspect-[9/18] rounded-[60px] p-[2px]"
                    style={{
                        background:
                            'linear-gradient(145deg, #4a4a4a 0%, #2d2d2d 50%, #1a1a1a 100%)',
                        boxShadow:
                            '0 25px 50px -12px rgba(0, 0, 0, 0.5), 0 0 0 1px rgba(255, 255, 255, 0.1), inset 0 1px 0 rgba(255, 255, 255, 0.15)'
                    }}
                >
                    {/* Inner bezel */}
                    <div className="relative w-full h-full bg-[#1a1a1a] rounded-[58px] p-[12px]">
                        {/* Screen area */}
                        <div className="relative w-full h-full bg-black rounded-[48px] overflow-hidden">
                            {/* Safe area top - status bar like real iPhone */}
                            <div className="absolute top-0 left-0 right-0 h-[34px] bg-black z-10 pointer-events-none">
                                {/* Status bar content */}
                                <div className="flex items-center justify-between px-8 pt-[14px] h-[34px]">
                                    {/* Left side - Time */}
                                    <span className="text-white text-xs font-semibold w-[54px]">
                                        {dayjs().format('HH:mm')}
                                    </span>

                                    {/* Center - Dynamic Island */}
                                    <div className="relative w-[126px] h-8 bg-black rounded-[20px]">
                                        {/* Left camera/sensor area */}
                                        <div className="absolute left-[22px] top-1/2 -translate-y-1/2 w-[11px] h-[11px] rounded-full bg-[#1c1c1e]">
                                            <div className="absolute inset-[2px] rounded-full bg-[#2c2c34]">
                                                <div className="absolute inset-[1px] rounded-full bg-[#0a0a12]" />
                                            </div>
                                        </div>
                                        {/* Right camera lens */}
                                        <div className="absolute right-[22px] top-1/2 -translate-y-1/2 w-[11px] h-[11px] rounded-full bg-[#1c1c1e]">
                                            <div className="absolute inset-[2px] rounded-full bg-[#080818]">
                                                <div className="absolute top-[1px] left-[1px] w-[2px] h-[2px] rounded-full bg-[#2a2a4a] opacity-60" />
                                            </div>
                                        </div>
                                    </div>

                                    {/* Right side - Status icons */}
                                    <div className="flex items-center gap-[5px] w-[77px] justify-end">
                                        {/* Cellular signal bars */}
                                        <svg
                                            width="14"
                                            height="12"
                                            viewBox="0 0 18 12"
                                            fill="none"
                                        >
                                            <rect
                                                x="0"
                                                y="8"
                                                width="3"
                                                height="4"
                                                rx="1"
                                                fill="currentColor"
                                            />
                                            <rect
                                                x="5"
                                                y="5"
                                                width="3"
                                                height="7"
                                                rx="1"
                                                fill="currentColor"
                                            />
                                            <rect
                                                x="10"
                                                y="2"
                                                width="3"
                                                height="10"
                                                rx="1"
                                                fill="currentColor"
                                            />
                                            <rect
                                                x="15"
                                                y="0"
                                                width="3"
                                                height="12"
                                                rx="1"
                                                fill="currentColor"
                                            />
                                        </svg>
                                        {/* WiFi icon */}
                                        <svg
                                            width="14"
                                            height="12"
                                            viewBox="0 0 17 12"
                                            fill="none"
                                        >
                                            <path
                                                d="M8.5 2.4C11.26 2.4 13.74 3.46 15.56 5.22C15.86 5.5 16.34 5.48 16.62 5.18C16.9 4.88 16.88 4.4 16.58 4.12C14.46 2.08 11.62 0.8 8.5 0.8C5.38 0.8 2.54 2.08 0.42 4.12C0.12 4.4 0.1 4.88 0.38 5.18C0.66 5.48 1.14 5.5 1.44 5.22C3.26 3.46 5.74 2.4 8.5 2.4Z"
                                                fill="currentColor"
                                            />
                                            <path
                                                d="M8.5 5.6C10.46 5.6 12.24 6.36 13.56 7.62C13.86 7.9 14.34 7.88 14.62 7.58C14.9 7.28 14.88 6.8 14.58 6.52C12.96 4.98 10.84 4 8.5 4C6.16 4 4.04 4.98 2.42 6.52C2.12 6.8 2.1 7.28 2.38 7.58C2.66 7.88 3.14 7.9 3.44 7.62C4.76 6.36 6.54 5.6 8.5 5.6Z"
                                                fill="currentColor"
                                            />
                                            <path
                                                d="M8.5 8.8C9.66 8.8 10.72 9.26 11.52 10.02C11.82 10.3 12.3 10.28 12.58 9.98C12.86 9.68 12.84 9.2 12.54 8.92C11.46 7.9 10.04 7.2 8.5 7.2C6.96 7.2 5.54 7.9 4.46 8.92C4.16 9.2 4.14 9.68 4.42 9.98C4.7 10.28 5.18 10.3 5.48 10.02C6.28 9.26 7.34 8.8 8.5 8.8Z"
                                                fill="currentColor"
                                            />
                                            <circle
                                                cx="8.5"
                                                cy="11"
                                                r="1"
                                                fill="currentColor"
                                            />
                                        </svg>
                                        {/* Battery icon */}
                                        <svg
                                            width="24"
                                            height="13"
                                            viewBox="0 0 27 13"
                                            fill="none"
                                        >
                                            <rect
                                                x="0.5"
                                                y="0.5"
                                                width="23"
                                                height="12"
                                                rx="3.5"
                                                stroke="currentColor"
                                                strokeOpacity="0.35"
                                            />
                                            <rect
                                                x="2"
                                                y="2"
                                                width="20"
                                                height="9"
                                                rx="2"
                                                fill="currentColor"
                                            />
                                            <path
                                                d="M25 4.5V8.5C25.83 8.17 26.5 7.17 26.5 6.5C26.5 5.83 25.83 4.83 25 4.5Z"
                                                fill="currentColor"
                                                fillOpacity="0.4"
                                            />
                                        </svg>
                                    </div>
                                </div>
                            </div>

                            {mobileAppView}
                        </div>
                    </div>
                </div>

                {/* Side buttons - Left side */}
                {/* Silent switch */}
                <div
                    className="absolute left-[-3px] top-[105px] w-[4px] h-[32px] rounded-l-[2px]"
                    style={{
                        background:
                            'linear-gradient(90deg, #3a3a3a 0%, #2a2a2a 100%)'
                    }}
                />
                {/* Volume Up */}
                <div
                    className="absolute left-[-3px] top-[158px] w-[4px] h-[65px] rounded-l-[2px]"
                    style={{
                        background:
                            'linear-gradient(90deg, #3a3a3a 0%, #2a2a2a 100%)'
                    }}
                />
                {/* Volume Down */}
                <div
                    className="absolute left-[-3px] top-[238px] w-[4px] h-[65px] rounded-l-[2px]"
                    style={{
                        background:
                            'linear-gradient(90deg, #3a3a3a 0%, #2a2a2a 100%)'
                    }}
                />

                {/* Side button - Right side (Power) */}
                <div
                    className="absolute right-[-3px] top-[190px] w-[4px] h-[95px] rounded-r-[2px]"
                    style={{
                        background:
                            'linear-gradient(270deg, #3a3a3a 0%, #2a2a2a 100%)'
                    }}
                />
            </div>

            {/* QR Code Section */}
            <div className="flex flex-col items-start gap-6 max-w-[300px]">
                <h2 className="text-xl font-semibold">
                    {t('agent.mobileResult.testOnPhone')}
                </h2>

                {/* QR Code */}
                <div className="bg-white p-4 rounded-xl">
                    <QRCode value={qrCodeUrl} size={180} level="H" />
                </div>

                {/* Scan instructions */}
                <div className="space-y-2">
                    <h3 className="font-semibold">
                        {isExpoGoQR
                            ? t('agent.mobileResult.scanToInstallExpo')
                            : t('agent.mobileResult.scanToTest')}
                    </h3>
                    <p className="text-gray-400 text-sm">
                        {t('agent.mobileResult.toTestOnDevice')}
                    </p>
                    <ol className="text-gray-400 text-sm list-decimal list-inside space-y-1">
                        <li>{t('agent.mobileResult.installExpoGo')}</li>
                        <li>{t('agent.mobileResult.openCamera')}</li>
                        <li>{t('agent.mobileResult.scanQrCode')}</li>
                    </ol>
                </div>

                {/* Browser preview note */}
                <div className="flex items-start gap-3 p-4 bg-[#2a2a2a] rounded-xl">
                    <Icon
                        name="info-circle"
                        className="w-5 h-5 stroke-gray-400 flex-shrink-0 mt-0.5"
                    />
                    <p className="text-gray-400 text-sm leading-relaxed">
                        {t('agent.mobileResult.browserNote')}
                    </p>
                </div>

                {/* Refresh button */}
                <button
                    onClick={handleRefresh}
                    className="flex items-center gap-2 px-4 py-2 text-white bg-[#2a2a2a] hover:bg-[#3a3a3a] rounded-lg transition-colors cursor-pointer"
                >
                    <Icon name="refresh" className="w-4 h-4 stroke-white" />
                    <span className="text-sm">
                        {t('agent.mobileResult.refresh')}
                    </span>
                </button>
            </div>
        </div>
    )
}

export default MobileResult
