// GenerateImageStep.tsx
import React, { useState, useEffect, useRef, useMemo } from "react";
import { Textarea, Button, Card, CardBody, Spinner } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faUpload, faWandMagicSparkles } from "@fortawesome/free-solid-svg-icons";

import { useAxios } from "@/hooks/axiosContext";
import { generate } from "@/apis/modelController";
import {
  deleteImage,
  getImagesByProject,
  uploadImage,
} from "@/apis/imageController";
import { createGenerationHistory, GenerationHistoryItem } from "@/apis/generationHistoryController";
import { getModelTypes } from "@/apis/modelProjectController";
import ImageGrid from "@/components/images/imageGrid";
import GenerationHistoryList from "@/components/steps/modelProjects/generationHistoryList";

type ReferenceImageConfig = {
  required: boolean;
  min: number;
  max: number;
  description?: string;
};

type ReferenceImage = {
  id: string;
  name?: string;
};

type GenerateImageStepProps = {
  projectId: string;
  project?: any;
  modelTypeInfo?: any;
};

const GenerateImageStep: React.FC<GenerateImageStepProps> = ({
  projectId,
  project,
  modelTypeInfo,
}) => {
  const { axiosInstance } = useAxios();
  const [prompt, setPrompt] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [referenceConfig, setReferenceConfig] = useState<ReferenceImageConfig | null>(null);
  const [referenceImages, setReferenceImages] = useState<ReferenceImage[]>([]);
  const [usedReferenceImageIds, setUsedReferenceImageIds] = useState<string[]>([]);
  const [isLoadingReferenceImages, setIsLoadingReferenceImages] = useState(false);
  const [isUploadingReferenceImages, setIsUploadingReferenceImages] = useState(false);
  const referenceInputRef = useRef<HTMLInputElement>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);

  useEffect(() => {
    const configFromProps = modelTypeInfo?.reference_images;
    if (configFromProps) {
      setReferenceConfig(configFromProps);
      return;
    }

    const loadReferenceConfig = async () => {
      if (!project?.model_type) {
        setReferenceConfig(null);
        return;
      }
      try {
        const response = await getModelTypes(axiosInstance);
        const typeInfo = (response.modelTypes || []).find(
          (type: any) => type.id === project.model_type,
        );
        setReferenceConfig(typeInfo?.reference_images || null);
      } catch (err) {
        console.error("Failed to load model metadata", err);
        setReferenceConfig(null);
      }
    };

    loadReferenceConfig();
  }, [axiosInstance, project?.model_type, modelTypeInfo]);

  useEffect(() => {
    fetchReferenceImages();
  }, [axiosInstance, projectId]);

  const fetchReferenceImages = async () => {
    if (!projectId) return;
    setIsLoadingReferenceImages(true);
    try {
      const response = await getImagesByProject(axiosInstance, projectId, "reference");
      const items = (response.images || []).map((img: any) => ({
        id: img.id,
        name: img.filename || "Image",
      }));
      setReferenceImages(items);
    } catch (err) {
      console.error("Failed to load reference images", err);
    } finally {
      setIsLoadingReferenceImages(false);
    }
  };

  const handleReferenceUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    if (!projectId) return;
    const files = Array.from(event.target.files || []);
    event.target.value = "";
    if (files.length === 0) return;

    if (referenceConfig?.max) {
      const availableSlots =
        referenceConfig.max - availableReferenceImages.length;
      if (availableSlots <= 0) {
        setError(`You can upload up to ${referenceConfig.max} reference image${referenceConfig.max === 1 ? "" : "s"}.`);
        return;
      }
      files.splice(availableSlots);
    }

    setIsUploadingReferenceImages(true);
    try {
      await uploadImage(
        axiosInstance,
        projectId,
        "reference_images",
        files,
        "reference",
        { normalize: false },
      );
      await fetchReferenceImages();
      setError(null);
    } catch (err) {
      console.error("Failed to upload reference images", err);
      setError("Failed to upload reference images. Please try again.");
    } finally {
      setIsUploadingReferenceImages(false);
    }
  };

  const handleRemoveReference = async (imageId: string) => {
    try {
      await deleteImage(axiosInstance, imageId);
      await fetchReferenceImages();
    } catch (err) {
      console.error("Failed to delete reference image", err);
      setError("Failed to delete reference image. Please try again.");
    }
  };

  const handleGenerate = async () => {
    const trimmedPrompt = prompt.trim();

    // Prevent empty submission
    if (!trimmedPrompt) {
      return;
    }

    if (referenceConfig?.required && referenceConfig.min > 0) {
      if (availableReferenceImages.length < referenceConfig.min) {
        setError(
          `Please upload at least ${referenceConfig.min} reference image${referenceConfig.min === 1 ? "" : "s"}.`,
        );
        return;
      }
    }

    setIsGenerating(true);
    setError(null);

    try {
      // Generate the image
      const referenceIds = availableReferenceImages.map((image) => image.id);
      const generatedImage = await generate(axiosInstance, trimmedPrompt, projectId, {
        referenceImageIds: referenceIds,
      });

      // Create history entry with the prompt and generated image
      await createGenerationHistory(
        axiosInstance,
        projectId,
        trimmedPrompt,
        [generatedImage.id],
        referenceIds,
      );

      // Clear the prompt input after successful generation
      setPrompt("");
      setReferenceImages((prev) => prev.filter((image) => !referenceIds.includes(image.id)));
      setUsedReferenceImageIds((prev) => Array.from(new Set([...prev, ...referenceIds])));
      setHistoryRefreshKey((prev) => prev + 1);
    } catch (err: any) {
      console.error("Generation error:", err);
      setError(
        err.response?.data?.error ||
          "Failed to generate image. Please try again.",
      );
    } finally {
      setIsGenerating(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !isGenerating && prompt.trim()) {
      handleGenerate();
    }
  };

  const usedReferenceIdSet = useMemo(
    () => new Set(usedReferenceImageIds),
    [usedReferenceImageIds],
  );

  const availableReferenceImages = useMemo(
    () => referenceImages.filter((image) => !usedReferenceIdSet.has(image.id)),
    [referenceImages, usedReferenceIdSet],
  );

  const handleHistoryLoaded = (histories: GenerationHistoryItem[]) => {
    const ids = new Set<string>();
    histories.forEach((item) => {
      (item.reference_image_ids || []).forEach((id: string | null) => {
        if (id) ids.add(id);
      });
    });
    setUsedReferenceImageIds(Array.from(ids));
  };

  const isReferenceRequirementMet =
    !referenceConfig?.required ||
    availableReferenceImages.length >= (referenceConfig?.min || 0);

  const canGenerate =
    prompt.trim().length > 0 && (!referenceConfig || isReferenceRequirementMet);

  return (
    <div>
      <h3 className="text-xl font-bold mb-4">Generate Image</h3>

      <Card className="mb-6">
        <CardBody className="space-y-4">
          <div>
        <Textarea
          className="mb-2"
          isDisabled={isGenerating}
          label="Enter your prompt"
          placeholder="Describe what you'd like to generate..."
          minRows={3}
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
        />

            {error && (
              <div className="mt-2 p-3 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 rounded-md text-sm">
                {error}
              </div>
            )}

            {isGenerating && (
              <div className="mt-3 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
                <Spinner size="sm" />
                <span>Generating image...</span>
              </div>
            )}
          </div>

          {referenceConfig && referenceConfig.max > 0 && (
            <div className="space-y-3">
              <div>
                <p className="font-semibold">Reference Images</p>
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {referenceConfig.description ||
                    "Upload reference images to guide generation."}
                </p>
                <p className="text-xs text-gray-500 mt-1">
                  {referenceConfig.required
                    ? `Required (${referenceConfig.min} image${referenceConfig.min === 1 ? "" : "s"})`
                    : "Optional"}
                  {referenceConfig.max
                    ? ` • Up to ${referenceConfig.max} image${referenceConfig.max === 1 ? "" : "s"}`
                    : ""}
                </p>
              </div>
              <div className="flex items-center gap-3">
                <input
                  type="file"
                  accept="image/*"
                  multiple={referenceConfig.max > 1}
                  className="hidden"
                  ref={referenceInputRef}
                  disabled={isGenerating}
                  onChange={handleReferenceUpload}
                />
                <Button
                  color="primary"
                  startContent={<FontAwesomeIcon icon={faUpload} />}
                  variant="flat"
                  isLoading={isUploadingReferenceImages}
                  isDisabled={isUploadingReferenceImages || isGenerating}
                  onPress={() => referenceInputRef.current?.click()}
                >
                  {availableReferenceImages.length ? "Add More" : "Upload Reference"}
                </Button>
                {!isGenerating &&
                  referenceConfig.required &&
                  availableReferenceImages.length < referenceConfig.min && (
                    <span className="text-xs text-danger">
                      Need {referenceConfig.min - availableReferenceImages.length} more image
                      {referenceConfig.min - availableReferenceImages.length === 1 ? "" : "s"}
                    </span>
                  )}
              </div>
              {availableReferenceImages.length > 0 ? (
              <div className="space-y-2 w-full">
                <p className="text-sm text-gray-600 dark:text-gray-400">
                  {availableReferenceImages.length} reference image
                  {availableReferenceImages.length === 1 ? "" : "s"} uploaded
                </p>
                  <ImageGrid
                    images={availableReferenceImages}
                    showModal={false}
                    thumbnailWidth={120}
                    thumbnailHeight={120}
                    isLoading={isLoadingReferenceImages}
                    showDeleteButton={!isGenerating}
                    onImageDelete={
                      !isGenerating
                        ? (imageId) => imageId && handleRemoveReference(imageId)
                        : undefined
                    }
                  />
                </div>
              ) : (
                <div className="rounded-lg border-2 border-dashed border-default-300 dark:border-default-600 p-4 text-sm text-gray-600 dark:text-gray-400">
                  No reference images uploaded. Add one above to guide generation.
                </div>
              )}
            </div>
          )}

          <div className="flex justify-end">
            <Button
              color="primary"
              isDisabled={!canGenerate || isGenerating}
              isLoading={isGenerating}
              startContent={!isGenerating ? <FontAwesomeIcon icon={faWandMagicSparkles} /> : undefined}
              onPress={handleGenerate}
            >
              {isGenerating ? "Generating..." : "Generate Image"}
            </Button>
          </div>
        </CardBody>
      </Card>

      <GenerationHistoryList
        projectId={projectId}
        refreshSignal={historyRefreshKey}
        onHistoryLoaded={handleHistoryLoaded}
      />
    </div>
  );
};

export default GenerateImageStep;
