// GenerateImageStep.tsx
import React, { useState, useEffect } from "react";
import { Input, Button, Card, CardBody, Image, Spinner, Chip } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faTrash } from "@fortawesome/free-solid-svg-icons";
import { useDisclosure } from "@heroui/react";

import { useAxios } from "@/hooks/axiosContext";
import { generate } from "@/apis/modelController";
import { downloadImageById, deleteImage } from "@/apis/imageController";
import {
  createGenerationHistory,
  listGenerationHistory,
  deleteGenerationHistory,
  GenerationHistoryItem,
} from "@/apis/generationHistoryController";

type GenerateImageStepProps = {
  projectId: string;
};

const GenerateImageStep: React.FC<GenerateImageStepProps> = ({ projectId }) => {
  const { axiosInstance } = useAxios();
  const [prompt, setPrompt] = useState<string>("");
  const [isGenerating, setIsGenerating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<GenerationHistoryItem[]>([]);
  const [isLoadingHistory, setIsLoadingHistory] = useState(true);
  const [thumbnails, setThumbnails] = useState<{ [imageId: string]: string }>(
    {},
  );
  const [selectedImage, setSelectedImage] = useState<{
    imageId: string;
    imageName: string;
  } | null>(null);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const [deleteConfirm, setDeleteConfirm] = useState<string | null>(null);

  // Fetch generation history on load
  useEffect(() => {
    fetchHistory();
  }, []);

  const fetchHistory = async () => {
    setIsLoadingHistory(true);
    try {
      const histories = await listGenerationHistory(axiosInstance, projectId);

      setHistory(histories);

      // Fetch thumbnails for all images
      histories.forEach((h) => {
        h.image_ids.forEach((imageId) => {
          if (!thumbnails[imageId]) {
            fetchThumbnail(imageId);
          }
        });
      });
    } catch (err) {
      console.error("Error fetching generation history:", err);
    } finally {
      setIsLoadingHistory(false);
    }
  };

  const fetchThumbnail = async (imageId: string) => {
    try {
      const response = await downloadImageById(axiosInstance, imageId);
      const reader = new FileReader();

      reader.onloadend = () => {
        setThumbnails((prev) => ({
          ...prev,
          [imageId]: reader.result as string,
        }));
      };
      reader.readAsDataURL(response);
    } catch (err) {
      console.error("Error fetching thumbnail:", err);
    }
  };

  const handleGenerate = async () => {
    const trimmedPrompt = prompt.trim();

    // Prevent empty submission
    if (!trimmedPrompt) {
      return;
    }

    setIsGenerating(true);
    setError(null);

    try {
      // Generate the image
      const generatedImage = await generate(
        axiosInstance,
        trimmedPrompt,
        projectId,
      );

      // Create history entry with the prompt and generated image
      const historyEntry = await createGenerationHistory(
        axiosInstance,
        projectId,
        trimmedPrompt,
        [generatedImage.id],
      );

      // Add to history (newest first)
      setHistory((prev) => [historyEntry, ...prev]);

      // Fetch thumbnail for the new image
      fetchThumbnail(generatedImage.id);

      // Clear the prompt input after successful generation
      setPrompt("");
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

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && !isGenerating && prompt.trim()) {
      handleGenerate();
    }
  };

  const handleDeleteRow = async (historyId: string) => {
    // Show confirmation
    if (deleteConfirm !== historyId) {
      setDeleteConfirm(historyId);

      return;
    }

    try {
      // Delete the history entry
      await deleteGenerationHistory(axiosInstance, historyId);

      // Find the history entry to delete its images
      const historyEntry = history.find((h) => h.id === historyId);

      // Delete associated images
      if (historyEntry) {
        await Promise.all(
          historyEntry.image_ids.map((imageId) =>
            deleteImage(axiosInstance, imageId).catch((err) =>
              console.error(`Failed to delete image ${imageId}:`, err),
            ),
          ),
        );
      }

      // Remove from state
      setHistory((prev) => prev.filter((h) => h.id !== historyId));
      setDeleteConfirm(null);
    } catch (err) {
      console.error("Error deleting history row:", err);
      setError("Failed to delete generation. Please try again.");
    }
  };

  const handleImageClick = (imageId: string, prompt: string) => {
    setSelectedImage({ imageId, imageName: prompt });
    onOpen();
  };

  const formatDate = (isoDate: string) => {
    const date = new Date(isoDate);

    return date.toLocaleString(undefined, {
      month: "short",
      day: "numeric",
      year: "numeric",
      hour: "numeric",
      minute: "2-digit",
    });
  };

  return (
    <div>
      <h3 className="text-xl font-bold mb-4">Generate Image</h3>

      {/* Prompt Input at the Top */}
      <div className="mb-6">
        <Input
          className="mb-2"
          disabled={isGenerating}
          label="Enter your prompt"
          placeholder="Type your prompt and press Enter..."
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
        />

        {/* Error Message */}
        {error && (
          <div className="mt-2 p-3 bg-red-100 dark:bg-red-900 text-red-800 dark:text-red-200 rounded-md text-sm">
            {error}
          </div>
        )}

        {/* Generating State */}
        {isGenerating && (
          <div className="mt-3 flex items-center gap-2 text-sm text-gray-600 dark:text-gray-400">
            <Spinner size="sm" />
            <span>Generating image...</span>
          </div>
        )}
      </div>

      {/* Generation History Rows */}
      <div className="space-y-4">
        {isLoadingHistory ? (
          <div className="flex justify-center py-8">
            <Spinner size="lg" />
          </div>
        ) : history.length === 0 ? (
          <div className="text-center py-8 text-gray-500 dark:text-gray-400">
            No generations yet. Enter a prompt above to get started.
          </div>
        ) : (
          history.map((item) => (
            <div className="flex flex-wrap gap-4">
              <div className="flex flex-wrap gap-4">
                {item.image_ids.map((imageId) => (
                  <div
                    key={imageId}
                    className="relative w-120 rounded-xl overflow-hidden"
                    onClick={() => handleImageClick(imageId, item.prompt)}
                  >
                    {thumbnails[imageId] ? (
                      <Image
                        alt="Generated image"
                        className="object-cover w-full h-full"
                        src={thumbnails[imageId]}
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center bg-gray-200 dark:bg-gray-700">
                        <Spinner size="sm" />
                      </div>
                    )}
                  </div>
                ))}
              </div>

              <div className="flex flex-col gap-2 justify-center">
                 <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {new Date(item.created_at).toLocaleDateString()} at{" "}
                      {new Date(item.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                <p className="text-gray-900 dark:text-gray-100">{item.prompt}</p>
                <div className="flex flex-wrap gap-2 items-center">
                  {item.user_profile?.display_name ? (
                      <p>By: {item.user_profile.display_name}</p>
                  ) : (
                      <p>User: {item.user_id.substring(0, 8)}...</p>
                  )}
                </div>

                <div className="mt-2">
                  {deleteConfirm === item.id ? (
                    <div className="flex gap-2 items-center">
                      <span className="text-sm text-gray-600 dark:text-gray-400">
                        Delete this generation?
                      </span>
                      <Button color="danger" size="sm" onPress={() => handleDeleteRow(item.id)}>
                        Confirm
                      </Button>
                      <Button size="sm" variant="light" onPress={() => setDeleteConfirm(null)}>
                        Cancel
                      </Button>
                    </div>
                  ) : (
                    <Button
                      color="danger"
                      size="sm"
                      variant="light"
                      isIconOnly
                      aria-label="Delete generation"
                      onPress={() => handleDeleteRow(item.id)}
                    >
                      <FontAwesomeIcon icon={faTrash} />
                    </Button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};

export default GenerateImageStep;
