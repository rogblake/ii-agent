import { ComponentProps, useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { X } from 'lucide-react'
import { Button } from '@/components/ui/button'

interface FullscreenImageModalProps {
    selectedImage: string | null
    onClose: () => void
}

export const FullscreenImageModal = ({
    selectedImage,
    onClose
}: FullscreenImageModalProps) => {
    return (
        <AnimatePresence>
            {selectedImage && (
                <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    exit={{ opacity: 0 }}
                    transition={{ duration: 0.2 }}
                    className="fixed inset-0 z-50 flex items-center justify-center bg-black/90 backdrop-blur-sm p-4"
                    onClick={onClose}
                >
                    <Button
                        variant="ghost"
                        size="icon"
                        className="absolute top-4 right-4 text-white hover:bg-white/10"
                        onClick={onClose}
                    >
                        <X className="size-6" />
                    </Button>
                    <motion.img
                        initial={{ scale: 0.9, opacity: 0 }}
                        animate={{ scale: 1, opacity: 1 }}
                        exit={{ scale: 0.9, opacity: 0 }}
                        transition={{ duration: 0.2 }}
                        src={selectedImage}
                        alt="Fullscreen image"
                        className="max-w-full max-h-full object-contain rounded-lg"
                        onClick={(e) => e.stopPropagation()}
                    />
                </motion.div>
            )}
        </AnimatePresence>
    )
}

interface ClickableImageProps extends ComponentProps<'img'> {
    src: string
    alt: string
    className?: string
}

export const ClickableImage = ({
    src,
    alt,
    className,
    ...props
}: ClickableImageProps) => {
    const [selectedImage, setSelectedImage] = useState<string | null>(null)

    return (
        <>
            <img
                {...props}
                src={src}
                alt={alt}
                className={`cursor-pointer ${className || ''}`}
                onClick={() => setSelectedImage(src)}
            />
            <FullscreenImageModal
                selectedImage={selectedImage}
                onClose={() => setSelectedImage(null)}
            />
        </>
    )
}
