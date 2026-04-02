import {
    selectAvailableModels,
    selectSelectedModel,
    useAppSelector
} from '@/state'

const ModelTag = () => {
    const selectedModel = useAppSelector(selectSelectedModel)
    const availableModels = useAppSelector(selectAvailableModels)

    const model = availableModels.find((m) => m.id === selectedModel)

    if (!selectedModel) return null

    return (
        <p className="model-tag bg-blue-gradient h-7 flex line-clamp-1 whitespace-pre justify-center items-center text-black text-[12px] font-bold px-4 rounded-[30px]">
            {model?.model}
        </p>
    )
}

export default ModelTag
