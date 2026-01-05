import React, { useRef, useState, useEffect, useMemo } from "react";
import { Button, Card, CardBody, Spinner, Chip } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faUpload,
  faWandMagicSparkles,
  faCheck,
  faExclamationCircle,
  faRotate,
  faPersonRunning,
  faTrash,
} from "@fortawesome/free-solid-svg-icons";

import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";
import {
  uploadImage,
  deleteImage,
  getDraftTrainingImages,
  getImageStatus,
} from "@/apis/imageController";
import {
  train,
  getTrainingRuns,
  updateTrainingRunStatus,
  deleteTrainingRun as deleteTrainingRunApi,
} from "@/apis/modelController";
import ImageGrid from "@/components/images/imageGrid";
import { getErrorMessage, logError } from "@/utils/errorHandling";

type ImageFile = {
  id: string;
  name: string;
  processing?: boolean;
};

type TrainingRun = {
  id: string;
  project_id: string;
  replicate_training_id: string | null;
  image_ids: string[];
  images?: ImageFile[];
  status: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  error_message: string | null;
};

type TrainingStepProps = {
  projectId: string;
  onTrainingComplete: () => void;
};

const TrainingStep: React.FC<TrainingStepProps> = ({
  projectId,
  onTrainingComplete,
}) => {
  const { axiosInstance } = useAxios();
  const { showError, showSuccess } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [images, setImages] = useState<ImageFile[]>([]);
  const [trainingRuns, setTrainingRuns] = useState<TrainingRun[]>([]);
  const [isUploadingImages, setIsUploadingImages] = useState(false);
  const [isLoadingImages, setIsLoadingImages] = useState(false);
  const [isLoadingTrainingRuns, setIsLoadingTrainingRuns] = useState(false);
  const [isStartingTraining, setIsStartingTraining] = useState(false);
  const [deletingRunId, setDeletingRunId] = useState<string | null>(null);
  const pollTimeoutRef = useRef<number | null>(null);
  const trainingPollRef = useRef<number | null>(null);
  const trainingPollInFlightRef = useRef(false);

  const ACTIVE_TRAINING_STATUSES = ["pending", "processing", "starting"];

  const allowedFileTypes = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
  ];
  const maxFileSize = 10 * 1024 * 1024; // 10MB

  useEffect(() => {
    if (projectId && projectId !== "new") {
      fetchImages();
      fetchTrainingRuns();
    }

    return () => {
      if (pollTimeoutRef.current) {
        window.clearTimeout(pollTimeoutRef.current);
      }
      if (trainingPollRef.current) {
        window.clearInterval(trainingPollRef.current);
      }
    };
  }, [projectId]);

  useEffect(() => {
    const hasActiveRuns = trainingRuns.some((run) =>
      ACTIVE_TRAINING_STATUSES.includes(run.status),
    );

    if (!hasActiveRuns) {
      if (trainingPollRef.current) {
        window.clearInterval(trainingPollRef.current);
        trainingPollRef.current = null;
      }
      return;
    }

    if (trainingPollRef.current) {
      return;
    }

    trainingPollRef.current = window.setInterval(async () => {
      if (trainingPollInFlightRef.current) {
        return;
      }
      trainingPollInFlightRef.current = true;
      try {
        const activeRuns = trainingRuns.filter((run) =>
          ACTIVE_TRAINING_STATUSES.includes(run.status),
        );
        if (!activeRuns.length) {
          return;
        }

        const updates = await Promise.all(
          activeRuns.map((run) => updateTrainingRunStatus(axiosInstance, run.id)),
        );

        const updatedById = new Map(updates.map((run) => [run.id, run]));
        setTrainingRuns((prev) => {
          const merged = prev.map((run) =>
            updatedById.has(run.id) ? { ...run, ...updatedById.get(run.id) } : run,
          );
          return merged;
        });

        const succeeded = updates.some((run) => run.status === "succeeded");
        if (succeeded) {
          showSuccess("Training completed successfully!");
          onTrainingComplete();
        }
      } catch (error) {
        logError("Poll training runs", error);
      } finally {
        trainingPollInFlightRef.current = false;
      }
    }, 5000);

    return () => {
      if (trainingPollRef.current) {
        window.clearInterval(trainingPollRef.current);
        trainingPollRef.current = null;
      }
    };
  }, [trainingRuns, axiosInstance, onTrainingComplete]);

  const fetchImages = async () => {
    if (!projectId || projectId === "new") return;

    setIsLoadingImages(true);
    try {
      const response = await getDraftTrainingImages(axiosInstance, projectId);
      const imageFiles: ImageFile[] = response.images.map((img: any) => ({
        id: img.id,
        name: img.filename || "Image",
        processing: img.processing,
      }));

      setImages((prev) => {
        const prevById = new Map(prev.map((img) => [img.id, img]));
        return imageFiles.map((img) => {
          const existing = prevById.get(img.id);
          if (
            existing &&
            existing.name === img.name &&
            existing.processing === img.processing
          ) {
            return existing;
          }
          return img;
        });
      });
      const pendingIds = imageFiles
        .filter((img) => img.processing)
        .map((img) => img.id);
      if (pendingIds.length) {
        pollImageStatus(pendingIds);
      }
    } catch (error) {
      logError("Fetch images", error);
    } finally {
      setIsLoadingImages(false);
    }
  };

  const mergeImages = (updates: ImageFile[]) => {
    setImages((prev) => {
      const byId = new Map(prev.map((img) => [img.id, img]));
      updates.forEach((img) => {
        byId.set(img.id, { ...byId.get(img.id), ...img });
      });
      return Array.from(byId.values());
    });
  };

  const pollImageStatus = async (imageIds: string[]) => {
    if (!imageIds.length) return;

    try {
      const response = await getImageStatus(axiosInstance, imageIds);
      const updates: ImageFile[] = (response.images || []).map((img: any) => ({
        id: img.id,
        name: img.filename || "Image",
        processing: img.processing,
      }));

      mergeImages(updates);

      const stillProcessing = updates
        .filter((img) => img.processing)
        .map((img) => img.id);

      if (stillProcessing.length) {
        pollTimeoutRef.current = window.setTimeout(() => {
          pollImageStatus(stillProcessing);
        }, 2000);
      }
    } catch (error) {
      logError("Poll image status", error);
    }
  };

  const fetchTrainingRuns = async () => {
    if (!projectId || projectId === "new") return;

    setIsLoadingTrainingRuns(true);
    try {
      const response = await getTrainingRuns(axiosInstance, projectId);
      const runs = (response.training_runs || []).filter(
        (run: any) => run.status !== "draft",
      );

      setTrainingRuns(runs);
    } catch (error) {
      logError("Fetch training runs", error);
    } finally {
      setIsLoadingTrainingRuns(false);
    }
  };

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;

    if (!files) return;

    const filesToUpload: File[] = [];
    let errorMsg = "";

    for (let i = 0; i < files.length; i++) {
      const file = files[i];

      if (!allowedFileTypes.includes(file.type)) {
        errorMsg = `File ${file.name} is not a valid image type`;
        continue;
      }

      if (file.size > maxFileSize) {
        errorMsg = `File ${file.name} is too large (max 10MB)`;
        continue;
      }

      filesToUpload.push(file);
    }

    if (errorMsg) {
      showError(errorMsg);
    }

    if (filesToUpload.length === 0) {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      return;
    }

    await handleUpload(filesToUpload);

    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  };

  const handleUpload = async (filesToUpload: File[]) => {
    if (!projectId || projectId === "new") {
      showError("Project not found");

      return;
    }

    setIsUploadingImages(true);
    try {
      const response = await uploadImage(
        axiosInstance,
        projectId,
        "uploaded_images",
        filesToUpload,
        "training",
        { resize: false },
      );

      const newImages: ImageFile[] = (response.images || []).map((img: any) => ({
        id: img.id,
        name: img.filename || "Image",
        processing: img.processing,
      }));

      if (newImages.length) {
        mergeImages(newImages);
        const pendingIds = newImages
          .filter((img) => img.processing)
          .map((img) => img.id);
        if (pendingIds.length) {
          pollImageStatus(pendingIds);
        }
      }
      showSuccess(
        `Uploaded ${filesToUpload.length} image${filesToUpload.length > 1 ? "s" : ""}. Processing started.`,
      );
    } catch (error) {
      logError("Upload images", error);
      showError(
        getErrorMessage(error, "Failed to upload images. Please try again."),
      );
    } finally {
      setIsUploadingImages(false);
    }
  };

  const isImageUsedInTraining = (imageId: string) => {
    return trainingRuns.some((run) => run.image_ids.includes(imageId));
  };

  const hasActiveTraining = useMemo(
    () => trainingRuns.some((run) => ACTIVE_TRAINING_STATUSES.includes(run.status)),
    [trainingRuns],
  );
  const hasProcessingImages = useMemo(
    () => images.some((img) => img.processing),
    [images],
  );

  const handleImageDelete = async (imageId: string) => {
    if (isImageUsedInTraining(imageId)) {
      showError("Cannot delete image that has been used in a training run");

      return;
    }

    try {
      await deleteImage(axiosInstance, imageId);
      setImages((prevImages) => prevImages.filter((img) => img.id !== imageId));
      showSuccess("Image deleted");
    } catch (error: any) {
      logError("Delete image", error);
      showError(getErrorMessage(error, "Failed to delete image"));
    }
  };

  const handleStartTraining = async () => {
    if (images.length === 0) {
      showError("Please upload at least one image for training");

      return;
    }
    if (hasProcessingImages) {
      showError("Please wait for all images to finish processing before training.");
      return;
    }

    setIsStartingTraining(true);

    try {
      await train(axiosInstance, projectId);

      showSuccess("Training started! Refreshing training runs...");
      setImages([]);

      // Refresh training runs
      await fetchTrainingRuns();
      await fetchImages();
    } catch (error: any) {
      logError("Start training", error);
      showError(
        getErrorMessage(error, "Failed to start training. Please try again."),
      );
    } finally {
      setIsStartingTraining(false);
    }
  };

  const handleRefreshStatus = async (trainingRunId: string) => {
    try {
      const response = await updateTrainingRunStatus(
        axiosInstance,
        trainingRunId,
      );

      // Update the training run in state
      setTrainingRuns((prev) =>
        prev.map((run) =>
          run.id === trainingRunId ? { ...run, ...response } : run,
        ),
      );

      // If training succeeded, notify parent
      if (response.status === "succeeded") {
        showSuccess("Training completed successfully!");
        onTrainingComplete();
      }
    } catch (error) {
      logError("Refresh training status", error);
      showError("Failed to refresh training status");
    }
  };

  const getStatusColor = (status: string) => {
    switch (status) {
      case "succeeded":
        return "success";
      case "failed":
      case "canceled":
        return "danger";
      case "processing":
      case "starting":
        return "warning";
      default:
        return "default";
    }
  };

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "succeeded":
        return faCheck;
      case "failed":
      case "canceled":
        return faExclamationCircle;
      default:
        return faWandMagicSparkles;
    }
  };

  const handleDeleteTrainingRun = async (trainingRunId: string) => {
    const shouldDelete = window.confirm(
      "Delete this training run? Active runs will be cancelled with Replicate.",
    );
    if (!shouldDelete) return;

    setDeletingRunId(trainingRunId);
    try {
      await deleteTrainingRunApi(axiosInstance, trainingRunId);
      setTrainingRuns((prev) =>
        prev.filter((run) => run.id !== trainingRunId),
      );
      await fetchImages();
      showSuccess("Training run deleted");
    } catch (error) {
      logError("Delete training run", error);
      showError(
        getErrorMessage(error, "Failed to delete training run. Try again."),
      );
    } finally {
      setDeletingRunId(null);
    }
  };

  return (
    <div className="max-w-7xl mx-auto">
      <h4 className="text-lg font-semibold mb-4">Training Images</h4>

      {/* Section 1: Upload and Training Start */}
      <div className="mb-8">
        <Card>
          <CardBody className="p-6">
            <input
              ref={fileInputRef}
              multiple
              accept={allowedFileTypes.join(",")}
              className="hidden"
              type="file"
              onChange={handleFileChange}
            />

            <Button
              className="mb-4"
              color="primary"
              isDisabled={isUploadingImages}
              isLoading={isUploadingImages}
              startContent={<FontAwesomeIcon icon={faUpload} />}
              variant="flat"
              onPress={handleFileSelect}
            >
              {isUploadingImages ? "Uploading..." : "Select Images"}
            </Button>

            {/* Training Images Row */}
            {isLoadingImages && images.length === 0 ? (
              <div className="flex justify-center py-8">
                <Spinner size="lg" />
              </div>
            ) : images.length > 0 ? (
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  {images.length} image
                  {images.length !== 1 ? "s" : ""} ready
                </p>

                <ImageGrid
                  images={images}
                  isLoading={isLoadingImages}
                  onImageDelete={handleImageDelete}
                  showDeleteButton
                  thumbnailWidth={120}
                />

                {/* Start Training Button - right-aligned */}
                <div className="flex flex-col items-end mt-4 text-right">
                  <Button
                    color="primary"
                    isDisabled={
                      images.length === 0 ||
                      hasProcessingImages ||
                      isStartingTraining ||
                      hasActiveTraining
                    }
                    isLoading={isStartingTraining}
                    size="lg"
                    startContent={
                      <FontAwesomeIcon icon={faWandMagicSparkles} />
                    }
                    onPress={handleStartTraining}
                  >
                    {isStartingTraining
                      ? "Starting Training..."
                      : `Start Training with ${images.length} Image${images.length !== 1 ? "s" : ""}`}
                  </Button>
                  {hasActiveTraining && (
                    <p className="text-xs text-gray-500 mt-2">
                      A training run is currently processing. Please wait (this can take up to 30 minutes).
                    </p>
                  )}
                  {hasProcessingImages && (
                    <p className="text-xs text-gray-500 mt-2">
                      Images are still processing. Training will be enabled when processing completes.
                    </p>
                  )}
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg">
                <FontAwesomeIcon
                  className="mb-3 opacity-30"
                  icon={faUpload}
                  size="2x"
                />
                {images.length === 0 ? (
                  <>
                    <p>No draft training images yet</p>
                    <p className="text-sm mt-2">
                      Upload images to begin training your model
                    </p>
                  </>
                ) : (
                  <>
                    <p>No draft images available</p>
                    <p className="text-sm mt-2">
                      Upload new photos to start another training run
                    </p>
                  </>
                )}
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Section 2: Training Runs List */}
      <div>
        <h4 className="text-lg font-semibold mb-4">Training Runs</h4>

        {isLoadingTrainingRuns && (
          <div className="flex justify-center py-12">
            <Spinner size="lg" />
          </div>
        )}

        {!isLoadingTrainingRuns && trainingRuns.length === 0 && (
          <div className="text-center text-gray-500 dark:text-gray-400">
            <FontAwesomeIcon
              className="mb-3 opacity-30"
              icon={faWandMagicSparkles}
              size="2x"
            />
            <p>No training runs yet</p>
            <p className="text-sm mt-2">
              Upload images and click "Start Training" to create your first
              training run
            </p>
          </div>
        )}

        {!isLoadingTrainingRuns && trainingRuns.length > 0 && (
          <div className="space-y-3">
            {trainingRuns.map((run) => {
              const runImages =
                run.images && run.images.length
                  ? run.images
                  : run.image_ids.map((imageId) => ({ id: imageId, processing: false }));
              return (
              <div
                key={run.id}
                className="grid md:grid-cols-[minmax(0,2.5fr)_minmax(150px,1fr)] gap-6 items-start"
              >
                <ImageGrid
                  className="flex flex-wrap gap-2"
                  images={runImages}
                  thumbnailWidth={112}
                  thumbnailHeight={112}
                />

                <div className="flex flex-col gap-2 justify-center">
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {new Date(run.created_at).toLocaleDateString()} at{" "}
                      {new Date(run.created_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </p>
                    <p className="text-xs text-gray-500 mt-1">
                      {run.image_ids.length} training image
                      {run.image_ids.length !== 1 ? "s" : ""}
                    </p>
                  </div>
                  <div>
                    <Chip
                      className="capitalize p-3"
                      color={getStatusColor(run.status)}
                      size="sm"
                      startContent={
                        run.status === "processing" ? (
                          <FontAwesomeIcon
                            className="text-xs mr-1 animate-spin"
                            icon={faPersonRunning}
                          />
                        ) : (
                          <FontAwesomeIcon
                            className="text-xs mr-1"
                            icon={getStatusIcon(run.status)}
                          />
                        )
                      }
                      variant="flat"
                    >
                      {run.status}
                    </Chip>
                    {run.status !== "succeeded" &&
                      run.status !== "failed" &&
                      run.status !== "canceled" && (
                        <Button
                          className="text-xs h-6"
                          size="sm"
                          variant="light"
                          isIconOnly
                          aria-label="Refresh status"
                          onPress={() => handleRefreshStatus(run.id)}
                        >
                          <FontAwesomeIcon icon={faRotate} />
                        </Button>
                      )}
                  </div>
                  {run.status === "processing" && (
                    <p className="text-xs text-gray-500">
                      Training is processing. This can take up to 30 minutes.
                    </p>
                  )}
                    {run.error_message && (
                      <p className="text-xs text-danger">
                        {run.error_message}
                      </p>
                    )}
                  <Button
                    className="w-fit mt-2"
                    color="danger"
                    size="sm"
                    startContent={<FontAwesomeIcon icon={faTrash} />}
                    variant="light"
                    isDisabled={deletingRunId === run.id}
                    isLoading={deletingRunId === run.id}
                    onPress={() => handleDeleteTrainingRun(run.id)}
                  >
                    Delete Run
                  </Button>
                </div>
              </div>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
};

export default TrainingStep;
