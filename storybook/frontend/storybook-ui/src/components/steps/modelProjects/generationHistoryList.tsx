import React, { useCallback, useEffect, useRef, useState } from "react";
import {
  Button,
  Spinner,
  Chip,
  Dropdown,
  DropdownTrigger,
  DropdownMenu,
  DropdownItem,
} from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faEllipsisVertical,
  faTrash,
  faWandMagicSparkles,
} from "@fortawesome/free-solid-svg-icons";

import { useAxios } from "@/hooks/axiosContext";
import {
  GenerationHistoryItem,
  listGenerationHistory,
  deleteGenerationHistory,
  updateGenerationHistoryStatus,
} from "@/apis/generationHistoryController";
import { deleteImage } from "@/apis/imageController";
import ImageGrid from "@/components/images/imageGrid";

interface GenerationHistoryListProps {
  projectId: string;
  refreshSignal?: number;
  onImageClick?: (imageId: string, prompt: string) => void;
  onHistoryLoaded?: (history: GenerationHistoryItem[]) => void;
}

const GenerationHistoryList: React.FC<GenerationHistoryListProps> = ({
  projectId,
  refreshSignal = 0,
  onImageClick,
  onHistoryLoaded,
}) => {
  const { axiosInstance } = useAxios();
  const [history, setHistory] = useState<GenerationHistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [deleteConfirmId, setDeleteConfirmId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<number | null>(null);
  const pollInFlightRef = useRef(false);

  const fetchHistory = useCallback(async () => {
    if (!projectId) return;

    setIsLoading(true);
    setError(null);
    try {
      const histories = await listGenerationHistory(axiosInstance, projectId);
      setHistory(histories);
      onHistoryLoaded?.(histories);
    } catch (err) {
      console.error("Error fetching generation history:", err);
      setError("Failed to load generation history.");
    } finally {
      setIsLoading(false);
    }
  }, [axiosInstance, projectId]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory, refreshSignal]);

  useEffect(() => {
    const activeHistories = history.filter(
      (item) => item.status === "processing" && item.prediction_id,
    );

    if (pollRef.current) {
      window.clearInterval(pollRef.current);
      pollRef.current = null;
    }
    if (!activeHistories.length) {
      return;
    }

    pollRef.current = window.setInterval(async () => {
      if (pollInFlightRef.current) {
        return;
      }
      pollInFlightRef.current = true;
      try {
        const updates = await Promise.all(
          activeHistories.map((item) =>
            updateGenerationHistoryStatus(axiosInstance, item.id),
          ),
        );
        const updatedById = new Map(updates.map((item) => [item.id, item]));
        setHistory((prev) =>
          prev.map((item) =>
            updatedById.has(item.id) ? { ...item, ...updatedById.get(item.id) } : item,
          ),
        );
      } catch (err) {
        console.error("Failed to poll generation history", err);
      } finally {
        pollInFlightRef.current = false;
      }
    }, 5000);

    return () => {
      if (pollRef.current) {
        window.clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [history, axiosInstance]);

  const handleDelete = async (historyId: string) => {
    if (deleteConfirmId !== historyId) {
      setDeleteConfirmId(historyId);
      return;
    }

    try {
      const historyEntry = history.find((h) => h.id === historyId);
      await deleteGenerationHistory(axiosInstance, historyId);

      if (historyEntry) {
        await Promise.all(
          historyEntry.image_ids.map((imageId) =>
            deleteImage(axiosInstance, imageId).catch((err) =>
              console.error(`Failed to delete image ${imageId}:`, err),
            ),
          ),
        );
      }

      setHistory((prev) => prev.filter((item) => item.id !== historyId));
      setDeleteConfirmId(null);
    } catch (err) {
      console.error("Failed to delete generation:", err);
      setError("Failed to delete generation. Please try again.");
    }
  };

  const cancelDelete = () => setDeleteConfirmId(null);

  if (isLoading) {
    return (
      <div className="flex justify-center py-8">
        <Spinner size="lg" />
      </div>
    );
  }

  if (history.length === 0) {
    return (
      <div className="text-center py-8 text-gray-500 dark:text-gray-400">
        No generations yet. Enter a prompt above to get started.
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <div className="rounded-md bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-200 px-4 py-2 text-sm">
          {error}
        </div>
      )}
      {history.map((item) => (
        <div key={item.id} className="flex flex-wrap gap-4">
          {item.image_ids.length > 0 ? (
            <ImageGrid
              className="flex flex-wrap gap-4"
              images={item.image_ids.map((imageId) => ({
                id: imageId,
                processing: item.status !== "completed",
              }))}
              showModal={false}
              thumbnailWidth={120}
              thumbnailHeight={120}
              onImageClick={(imageId) => onImageClick?.(imageId, item.prompt)}
            />
          ) : (
            <div className="w-[120px] h-[120px] rounded-xl border border-default-700/60 bg-default-800/40 flex flex-col items-center justify-center text-xs text-gray-300">
              <FontAwesomeIcon className="mb-2 text-sm" icon={faWandMagicSparkles} />
              Generating...
            </div>
          )}

          <div className="relative flex flex-col gap-2 justify-center flex-1 min-w-[200px]">
            <div className="absolute top-0 right-0 z-10">
              <Dropdown placement="bottom-end">
                <DropdownTrigger>
                  <Button
                    className="text-xs h-6"
                    size="sm"
                    variant="light"
                    isIconOnly
                    aria-label="Generation actions"
                  >
                    <FontAwesomeIcon icon={faEllipsisVertical} />
                  </Button>
                </DropdownTrigger>
                <DropdownMenu aria-label="Generation actions" variant="flat">
                  <DropdownItem
                    key="delete"
                    color="danger"
                    onPress={() => handleDelete(item.id)}
                  >
                    Delete generation
                  </DropdownItem>
                </DropdownMenu>
              </Dropdown>
            </div>
            <div>
              <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                {new Date(item.created_at).toLocaleDateString()} at{" "}
                {new Date(item.created_at).toLocaleTimeString([], {
                  hour: "2-digit",
                  minute: "2-digit",
                })}
              </p>
              <p className="text-gray-900 dark:text-gray-100">{item.prompt}</p>
              {item.status && item.status !== "completed" && (
                <Chip className="mt-2 capitalize" color="warning" size="sm" variant="flat">
                  {item.status}
                </Chip>
              )}
              {item.status === "failed" && item.error_message && (
                <p className="text-xs text-danger mt-1">{item.error_message}</p>
              )}
            </div>

            {item.reference_image_ids && item.reference_image_ids.length > 0 && (
              <div className="mt-2">
                <p className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400 mb-2">
                  Reference Images
                </p>
                <ImageGrid
                  className="flex flex-wrap gap-2"
                  images={(item.reference_image_ids || [])
                    .filter(Boolean)
                    .map((referenceId) => ({
                      id: referenceId as string,
                      processing: false,
                    }))}
                  showModal={false}
                  thumbnailWidth={56}
                  thumbnailHeight={56}
                />
              </div>
            )}

            <div className="flex flex-wrap gap-2 items-center text-sm text-gray-700 dark:text-gray-300">
              {item.user_profile?.display_name ? (
                <p>By: {item.user_profile.display_name}</p>
              ) : (
                <p>User: {item.user_id.substring(0, 8)}...</p>
              )}
            </div>

            {deleteConfirmId === item.id && (
              <div className="flex gap-2 items-center">
                <span className="text-sm text-gray-600 dark:text-gray-400">
                  Delete this generation?
                </span>
                <Button color="danger" size="sm" onPress={() => handleDelete(item.id)}>
                  Confirm
                </Button>
                <Button size="sm" variant="light" onPress={cancelDelete}>
                  Cancel
                </Button>
              </div>
            )}
          </div>
        </div>
      ))}
    </div>
  );
};

export default GenerationHistoryList;
