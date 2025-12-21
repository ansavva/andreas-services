import React, { useRef, useState, useEffect } from "react";
import { Button, Card, CardBody, Spinner, Chip, Image } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faUpload, faWandMagicSparkles, faCheck, faExclamationCircle } from "@fortawesome/free-solid-svg-icons";
import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";
import { uploadImage, deleteImage, getImagesByProject, downloadImageById } from "@/apis/imageController";
import { train, getTrainingRuns, updateTrainingRunStatus } from "@/apis/modelController";
import ImageGrid from "@/components/images/imageGrid";
import { getErrorMessage, logError } from "@/utils/errorHandling";

type ImageFile = {
  id: string;
  name: string;
};

type TrainingRun = {
  id: string;
  project_id: string;
  replicate_training_id: string | null;
  image_ids: string[];
  status: string;
  created_at: string;
  updated_at: string;
  completed_at: string | null;
  error_message: string | null;
};

type ImageUploadStepProps = {
  projectId: string;
  project: any;
  onTrainingComplete: () => void;
};

const ImageUploadStep: React.FC<ImageUploadStepProps> = ({
  projectId,
  project,
  onTrainingComplete,
}) => {
  const { axiosInstance } = useAxios();
  const { showError, showSuccess } = useToast();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [images, setImages] = useState<ImageFile[]>([]);
  const [trainingRuns, setTrainingRuns] = useState<TrainingRun[]>([]);
  const [imageThumbnails, setImageThumbnails] = useState<Record<string, string>>({});
  const [isUploadingImages, setIsUploadingImages] = useState(false);
  const [isLoadingImages, setIsLoadingImages] = useState(false);
  const [isLoadingTrainingRuns, setIsLoadingTrainingRuns] = useState(false);
  const [isStartingTraining, setIsStartingTraining] = useState(false);

  const allowedFileTypes = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
  const maxFileSize = 10 * 1024 * 1024; // 10MB

  useEffect(() => {
    if (projectId && projectId !== "new") {
      fetchImages();
      fetchTrainingRuns();
    }
  }, [projectId]);

  const fetchImages = async () => {
    if (!projectId || projectId === "new") return;

    setIsLoadingImages(true);
    try {
      // Only fetch training images, not generated images
      const response = await getImagesByProject(axiosInstance, projectId, "training");
      const imageFiles = response.images.map((img: any) => ({
        id: img.id,
        name: img.filename || "Image",
      }));
      setImages(imageFiles);
    } catch (error) {
      logError("Fetch images", error);
    } finally {
      setIsLoadingImages(false);
    }
  };

  const fetchTrainingRuns = async () => {
    if (!projectId || projectId === "new") return;

    setIsLoadingTrainingRuns(true);
    try {
      const response = await getTrainingRuns(axiosInstance, projectId);
      const runs = response.training_runs || [];
      setTrainingRuns(runs);

      // Load thumbnails for all images in all training runs
      runs.forEach((run: TrainingRun) => {
        run.image_ids.forEach((imageId: string) => {
          if (!imageThumbnails[imageId]) {
            loadImageThumbnail(imageId);
          }
        });
      });
    } catch (error) {
      logError("Fetch training runs", error);
    } finally {
      setIsLoadingTrainingRuns(false);
    }
  };

  const loadImageThumbnail = async (imageId: string) => {
    try {
      const blob = await downloadImageById(axiosInstance, imageId);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImageThumbnails(prev => ({
          ...prev,
          [imageId]: reader.result as string
        }));
      };
      reader.readAsDataURL(blob);
    } catch (error) {
      logError(`Load thumbnail for ${imageId}`, error);
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
      await uploadImage(axiosInstance, projectId, "uploaded_images", filesToUpload, "training", { normalize: false });
      await fetchImages();
      showSuccess(`Successfully uploaded ${filesToUpload.length} image${filesToUpload.length > 1 ? 's' : ''}`);
    } catch (error) {
      logError("Upload images", error);
      showError(getErrorMessage(error, "Failed to upload images. Please try again."));
    } finally {
      setIsUploadingImages(false);
    }
  };

  const handleImageDelete = async (imageId: string) => {
    // Check if image is used in any training run
    const usedInTraining = trainingRuns.some(run => run.image_ids.includes(imageId));
    if (usedInTraining) {
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

    setIsStartingTraining(true);

    try {
      // Use all uploaded images for training
      const imageIdsArray = images.map(img => img.id);
      await train(axiosInstance, projectId, imageIdsArray);

      showSuccess("Training started! Refreshing training runs...");

      // Refresh training runs
      await fetchTrainingRuns();
    } catch (error: any) {
      logError("Start training", error);
      showError(getErrorMessage(error, "Failed to start training. Please try again."));
    } finally {
      setIsStartingTraining(false);
    }
  };

  const handleRefreshStatus = async (trainingRunId: string) => {
    try {
      const response = await updateTrainingRunStatus(axiosInstance, trainingRunId);

      // Update the training run in state
      setTrainingRuns(prev =>
        prev.map(run => run.id === trainingRunId ? { ...run, ...response } : run)
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

  return (
    <div className="max-w-7xl mx-auto">
      <h4 className="text-lg font-semibold mb-4">Training Images</h4>

      {/* Section 1: Upload and Training Start */}
      <div className="mb-8">
        <Card>
          <CardBody className="p-6">
            <input
              type="file"
              ref={fileInputRef}
              onChange={handleFileChange}
              accept={allowedFileTypes.join(",")}
              multiple
              className="hidden"
            />

            <Button
              color="primary"
              variant="flat"
              startContent={<FontAwesomeIcon icon={faUpload} />}
              onPress={handleFileSelect}
              isDisabled={isUploadingImages}
              isLoading={isUploadingImages}
              className="mb-4"
            >
              {isUploadingImages ? "Uploading..." : "Select Images"}
            </Button>

            {/* Training Images Row */}
            {images.length > 0 ? (
              <div>
                <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                  {images.length} image{images.length !== 1 ? "s" : ""} uploaded
                </p>

                <ImageGrid
                  images={images}
                  isLoading={isLoadingImages}
                  onImageDelete={handleImageDelete}
                  compact
                />

                {/* Start Training Button - right-aligned */}
                <div className="flex justify-end mt-4">
                  <Button
                    color="primary"
                    size="lg"
                    startContent={<FontAwesomeIcon icon={faWandMagicSparkles} />}
                    onPress={handleStartTraining}
                    isLoading={isStartingTraining}
                    isDisabled={images.length === 0 || isStartingTraining}
                  >
                    {isStartingTraining ? "Starting Training..." : `Start Training with ${images.length} Image${images.length !== 1 ? 's' : ''}`}
                  </Button>
                </div>
              </div>
            ) : (
              <div className="text-center py-8 text-gray-500 dark:text-gray-400 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg">
                <FontAwesomeIcon icon={faUpload} size="2x" className="mb-3 opacity-30" />
                <p>No training images uploaded yet</p>
                <p className="text-sm mt-2">Upload images to begin training your model</p>
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
          <Card>
            <CardBody className="p-8">
              <div className="text-center text-gray-500 dark:text-gray-400">
                <FontAwesomeIcon icon={faWandMagicSparkles} size="2x" className="mb-3 opacity-30" />
                <p>No training runs yet</p>
                <p className="text-sm mt-2">Select images and click "Start Training" to create your first training run</p>
              </div>
            </CardBody>
          </Card>
        )}

        {!isLoadingTrainingRuns && trainingRuns.length > 0 && (
          <div className="space-y-3">
            {trainingRuns.map((run) => (
              <Card key={run.id} className="border border-gray-200 dark:border-gray-700">
                <CardBody className="p-4">
                  {/* Row layout: thumbnails left, metadata right */}
                  <div className="flex items-start gap-4">
                    {/* Left: Image thumbnails */}
                    <div className="flex gap-2 flex-shrink-0">
                      {run.image_ids.slice(0, 4).map((imageId) => (
                        <div key={imageId} className="relative">
                          {imageThumbnails[imageId] ? (
                            <div className="relative w-16 h-16 rounded-lg overflow-hidden border border-gray-200 dark:border-gray-700">
                              <Image
                                src={imageThumbnails[imageId]}
                                alt="Training image"
                                width={64}
                                height={64}
                                className="object-cover"
                              />
                              {/* Small training badge on thumbnails */}
                              <div className="absolute bottom-0 right-0">
                                <Chip size="sm" color="primary" variant="flat" className="text-[8px] h-3 px-1">
                                  T
                                </Chip>
                              </div>
                            </div>
                          ) : (
                            <div className="w-16 h-16 bg-gray-200 dark:bg-gray-700 rounded-lg flex items-center justify-center">
                              <Spinner size="sm" />
                            </div>
                          )}
                        </div>
                      ))}
                      {run.image_ids.length > 4 && (
                        <div className="w-16 h-16 bg-gray-100 dark:bg-gray-800 rounded-lg flex items-center justify-center text-xs font-medium">
                          +{run.image_ids.length - 4}
                        </div>
                      )}
                    </div>

                    {/* Right: Metadata */}
                    <div className="flex-1 flex justify-between items-start">
                      <div>
                        <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">
                          {new Date(run.created_at).toLocaleDateString()} at {new Date(run.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                        </p>
                        <p className="text-xs text-gray-500 mt-1">
                          {run.image_ids.length} training image{run.image_ids.length !== 1 ? 's' : ''}
                        </p>
                        {run.error_message && (
                          <p className="text-xs text-danger mt-2">{run.error_message}</p>
                        )}
                      </div>

                      <div className="flex flex-col items-end gap-2">
                        <Chip
                          size="sm"
                          color={getStatusColor(run.status)}
                          variant="flat"
                          startContent={<FontAwesomeIcon icon={getStatusIcon(run.status)} className="text-xs" />}
                          className="capitalize"
                        >
                          {run.status}
                        </Chip>

                        {run.status !== "succeeded" && run.status !== "failed" && run.status !== "canceled" && (
                          <Button
                            size="sm"
                            variant="light"
                            onPress={() => handleRefreshStatus(run.id)}
                            className="text-xs h-6"
                          >
                            Refresh
                          </Button>
                        )}
                      </div>
                    </div>
                  </div>
                </CardBody>
              </Card>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default ImageUploadStep;
