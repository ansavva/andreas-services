// GenerateImageStep.tsx
import React, { useState, useEffect } from "react";
import { Input, Button, Card, Image, Spinner, Chip } from "@heroui/react";
import { useAxios } from "@/hooks/axiosContext";
import { generate } from "@/apis/modelController";
import { downloadImageById, deleteImage } from "@/apis/imageController";
import {
  createGenerationHistory,
  listGenerationHistory,
  deleteGenerationHistory,
  GenerationHistoryItem,
} from "@/apis/generationHistoryController";
import { useDisclosure } from "@heroui/react";
import ImageModal from "@/components/images/imageModal";

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
  const [thumbnails, setThumbnails] = useState<{ [imageId: string]: string }>({});
  const [selectedImage, setSelectedImage] = useState<{ imageId: string; imageName: string } | null>(null);
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
        setThumbnails((prev) => ({ ...prev, [imageId]: reader.result as string }));
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
      const generatedImage = await generate(axiosInstance, trimmedPrompt, projectId);

      // Create history entry with the prompt and generated image
      const historyEntry = await createGenerationHistory(
        axiosInstance,
        projectId,
        trimmedPrompt,
        [generatedImage.id]
      );

      // Add to history (newest first)
      setHistory((prev) => [historyEntry, ...prev]);

      // Fetch thumbnail for the new image
      fetchThumbnail(generatedImage.id);

      // Clear the prompt input after successful generation
      setPrompt("");
    } catch (err: any) {
      console.error("Generation error:", err);
      setError(err.response?.data?.error || "Failed to generate image. Please try again.");
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
              console.error(`Failed to delete image ${imageId}:`, err)
            )
          )
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
    <div className="mt-6">
      <h3 className="text-xl font-bold mb-4">Generate Image</h3>

      {/* Prompt Input at the Top */}
      <div className="mb-6">
        <Input
          label="Enter your prompt"
          value={prompt}
          onChange={(e) => setPrompt(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Type your prompt and press Enter..."
          description="Enter any prompt you want with the subject you see above."
          disabled={isGenerating}
          className="mb-2"
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
        <h4 className="text-lg font-semibold">Generation History</h4>

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
            <Card key={item.id} className="p-4">
              <div className="flex gap-4">
                {/* Left: Generated Images */}
                <div className="flex gap-2 flex-shrink-0">
                  {item.image_ids.map((imageId) => (
                    <div
                      key={imageId}
                      className="w-24 h-24 cursor-pointer"
                      onClick={() => handleImageClick(imageId, item.prompt)}
                    >
                      {thumbnails[imageId] ? (
                        <Image
                          src={thumbnails[imageId]}
                          alt="Generated image"
                          className="w-full h-full object-cover rounded-md"
                        />
                      ) : (
                        <div className="w-full h-full flex items-center justify-center bg-gray-200 dark:bg-gray-700 rounded-md">
                          <Spinner size="sm" />
                        </div>
                      )}
                    </div>
                  ))}
                </div>

                {/* Right: Prompt and Metadata */}
                <div className="flex-1 flex flex-col gap-2">
                  {/* Prompt Text (non-editable) */}
                  <p className="text-sm">{item.prompt}</p>

                  {/* Info Tags */}
                  <div className="flex flex-wrap gap-2 items-center">
                    <Chip size="sm" variant="flat">
                      {formatDate(item.created_at)}
                    </Chip>
                    {item.user_profile?.display_name ? (
                      <Chip size="sm" variant="flat">
                        By: {item.user_profile.display_name}
                      </Chip>
                    ) : (
                      <Chip size="sm" variant="flat" className="font-mono text-xs">
                        User: {item.user_id.substring(0, 8)}...
                      </Chip>
                    )}
                  </div>

                  {/* Delete Button */}
                  <div className="mt-auto">
                    {deleteConfirm === item.id ? (
                      <div className="flex gap-2 items-center">
                        <span className="text-sm text-gray-600 dark:text-gray-400">
                          Delete this generation?
                        </span>
                        <Button
                          size="sm"
                          color="danger"
                          onPress={() => handleDeleteRow(item.id)}
                        >
                          Confirm
                        </Button>
                        <Button
                          size="sm"
                          variant="light"
                          onPress={() => setDeleteConfirm(null)}
                        >
                          Cancel
                        </Button>
                      </div>
                    ) : (
                      <Button
                        size="sm"
                        color="danger"
                        variant="light"
                        onPress={() => handleDeleteRow(item.id)}
                      >
                        Delete
                      </Button>
                    )}
                  </div>
                </div>
              </div>
            </Card>
          ))
        )}
      </div>

      {/* Image Modal */}
      {selectedImage && (
        <ImageModal
          isOpen={isOpen}
          onClose={() => {
            onClose();
            setSelectedImage(null);
          }}
          imageSrc={thumbnails[selectedImage.imageId]}
          imageName={selectedImage.imageName}
          imageId={selectedImage.imageId}
          onImageDelete={() => {
            // Image deletion is handled at the row level
            onClose();
            setSelectedImage(null);
          }}
        />
      )}
    </div>
  );
};

export default GenerateImageStep;