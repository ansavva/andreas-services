import React, { useRef, useState, useEffect } from "react";
import { Button, Card, CardBody, Input, Spinner } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faUpload, faWandMagicSparkles, faCheck } from "@fortawesome/free-solid-svg-icons";
import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";
import { uploadImage, deleteImage, getImagesByProject } from "@/apis/imageController";
import { train, training_status } from "@/apis/modelController";
import { createModelProject } from "@/apis/modelProjectController";
import { useNavigate } from "react-router-dom";
import ImageGrid from "@/components/images/imageGrid";
import { getErrorMessage, logError } from "@/utils/errorHandling";

type ImageFile = {
  id: string;
  name: string;
};

type TrainingSetupStepProps = {
  projectId: string;
  project: any;
  onProjectCreated: (project: any) => void;
  onTrainingComplete: () => void;
};

const TrainingSetupStep: React.FC<TrainingSetupStepProps> = ({
  projectId,
  project,
  onProjectCreated,
  onTrainingComplete,
}) => {
  const { axiosInstance } = useAxios();
  const { showError, showSuccess } = useToast();
  const navigate = useNavigate();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Subject name state (only for new projects)
  const [subjectName, setSubjectName] = useState("");
  const [subjectNameError, setSubjectNameError] = useState("");

  // Images state
  const [images, setImages] = useState<ImageFile[]>([]);
  const [isUploadingImages, setIsUploadingImages] = useState(false);
  const [isLoadingImages, setIsLoadingImages] = useState(false);

  // Training state
  const [isTraining, setIsTraining] = useState(false);
  const [trainingStatus, setTrainingStatus] = useState<string>("pending");
  const [trainingComplete, setTrainingComplete] = useState(false);

  const allowedFileTypes = ["image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"];
  const maxFileSize = 10 * 1024 * 1024; // 10MB

  // Load existing images if project exists
  useEffect(() => {
    if (projectId && projectId !== "new") {
      fetchImages();
    }
  }, [projectId]);

  const fetchImages = async () => {
    if (!projectId || projectId === "new") return;

    setIsLoadingImages(true);
    try {
      const response = await getImagesByProject(axiosInstance, projectId);
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
      showError("Please start training first to create the project");
      return;
    }

    setIsUploadingImages(true);
    try {
      await uploadImage(axiosInstance, projectId, "uploaded_images", filesToUpload);
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
    // Validate subject name for new projects
    if (projectId === "new") {
      if (!subjectName.trim()) {
        setSubjectNameError("Subject name is required");
        return;
      }
      setSubjectNameError("");
    }

    if (images.length === 0) {
      showError("Please upload at least one image before training");
      return;
    }

    setIsTraining(true);
    setTrainingStatus("pending");

    try {
      let currentProjectId = projectId;

      // If this is a new model project, create it first
      if (projectId === "new") {
        const newProject = await createModelProject(axiosInstance, subjectName, subjectName);
        onProjectCreated(newProject);
        currentProjectId = newProject.id;

        // Update URL to reflect the actual model project ID
        navigate(`/model-project/${newProject.id}`, { replace: true });

        // Upload images to the newly created project
        if (fileInputRef.current?.files) {
          const files = Array.from(fileInputRef.current.files);
          await uploadImage(axiosInstance, currentProjectId, "uploaded_images", files);
        }
      }

      // Start training
      const response = await train(axiosInstance, currentProjectId, "uploaded_images");
      setTrainingStatus("running");
      await pollTrainingStatus(response.training_id);
    } catch (error: any) {
      logError("Start training", error);
      showError(getErrorMessage(error, "Failed to start training. Please try again."));
      setIsTraining(false);
      setTrainingStatus("failed");
    }
  };

  const pollTrainingStatus = async (training_id: string) => {
    const intervalId = setInterval(async () => {
      try {
        const { status } = await training_status(axiosInstance, training_id);
        setTrainingStatus(status);
        if (status === "succeeded") {
          clearInterval(intervalId);
          setIsTraining(false);
          setTrainingComplete(true);
          showSuccess("Training completed successfully!");
        } else if (status === "failed") {
          clearInterval(intervalId);
          setIsTraining(false);
          showError("Training failed. Please try again.");
        }
      } catch (error) {
        clearInterval(intervalId);
        setTrainingStatus("failed");
        setIsTraining(false);
        showError("Failed to check training status");
      }
    }, 5000);
  };

  const canStartTraining = projectId === "new" ? subjectName.trim() && images.length > 0 : images.length > 0;

  return (
    <div className="max-w-7xl mx-auto">
      <h3 className="text-2xl font-bold mb-2">Train Your Model</h3>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        {projectId === "new"
          ? "Enter a name for your subject and upload images to train your AI model."
          : `Upload images of ${project?.subjectName || 'your subject'} and start training your AI model.`}
      </p>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Left Panel: Controls */}
        <div className="space-y-4">
          {/* Subject Name Input (only for new projects) */}
          {projectId === "new" && (
            <Card>
              <CardBody className="p-6">
                <h4 className="text-lg font-semibold mb-3">Subject Information</h4>
                <Input
                  label="Subject Name"
                  placeholder="e.g., John, My Dog, etc."
                  value={subjectName}
                  onValueChange={(value) => {
                    setSubjectName(value);
                    if (value.trim()) setSubjectNameError("");
                  }}
                  isInvalid={!!subjectNameError}
                  errorMessage={subjectNameError}
                  isRequired
                  variant="bordered"
                  isDisabled={isTraining || trainingComplete}
                />
              </CardBody>
            </Card>
          )}

          {/* Photo Upload */}
          <Card>
            <CardBody className="p-6">
              <h4 className="text-lg font-semibold mb-3">Upload Training Images</h4>
              <p className="text-sm text-gray-600 dark:text-gray-400 mb-4">
                Upload images (JPG, PNG, HEIC) of your subject
              </p>

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
                isDisabled={isUploadingImages || isTraining || trainingComplete || (projectId === "new")}
                isLoading={isUploadingImages}
                className="mb-4"
              >
                {isUploadingImages ? "Uploading..." : "Select Images"}
              </Button>

              {(projectId === "new") && (
                <p className="text-sm text-warning mb-4">
                  Note: You'll be able to upload images after starting training
                </p>
              )}

              {images.length > 0 && (
                <div>
                  <p className="text-sm text-gray-600 dark:text-gray-400 mb-2">
                    {images.length} image{images.length > 1 ? "s" : ""} uploaded
                  </p>
                  <ImageGrid
                    images={images}
                    isLoading={isLoadingImages}
                    onImageDelete={isTraining || trainingComplete ? undefined : handleImageDelete}
                  />
                </div>
              )}
            </CardBody>
          </Card>

          {/* Start Training Button */}
          {!trainingComplete && (
            <Button
              color="primary"
              size="lg"
              className="w-full"
              startContent={<FontAwesomeIcon icon={faWandMagicSparkles} />}
              onPress={handleStartTraining}
              isLoading={isTraining}
              isDisabled={!canStartTraining || isTraining}
            >
              {isTraining ? "Training..." : "Start Training"}
            </Button>
          )}
        </div>

        {/* Right Panel: Training Status */}
        <Card>
          <CardBody className="p-6 min-h-[600px] flex flex-col items-center justify-center">
            {!isTraining && !trainingComplete && (
              <div className="text-center text-gray-500 dark:text-gray-400">
                <FontAwesomeIcon icon={faWandMagicSparkles} size="3x" className="mb-4 opacity-30" />
                <p>Training status will appear here</p>
                <p className="text-sm mt-2">Upload images and click "Start Training" to begin</p>
              </div>
            )}

            {isTraining && (
              <div className="text-center">
                <Spinner size="lg" />
                <p className="mt-4 text-lg font-semibold">Training in Progress</p>
                <p className="mt-2 text-gray-600 dark:text-gray-400">
                  {trainingStatus === "pending" || trainingStatus === "processing"
                    ? "This could take a while. Please don't leave this screen."
                    : `Status: ${trainingStatus}`}
                </p>
              </div>
            )}

            {trainingComplete && (
              <div className="text-center w-full">
                <div className="mb-4">
                  <FontAwesomeIcon icon={faCheck} size="3x" className="text-success" />
                </div>
                <h4 className="text-xl font-bold text-success mb-2">Training Complete!</h4>
                <p className="text-gray-600 dark:text-gray-400 mb-6">
                  Your model for <strong>{project?.subjectName || subjectName}</strong> is ready to use.
                </p>
                <div className="bg-success-50 dark:bg-success-900/20 p-4 rounded-lg">
                  <p className="text-sm text-success-700 dark:text-success-300">
                    You can now generate images with your trained model!
                  </p>
                </div>

                <Button
                  color="primary"
                  size="lg"
                  className="mt-6 w-full"
                  onPress={onTrainingComplete}
                >
                  Continue to Generate Images
                </Button>
              </div>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
};

export default TrainingSetupStep;
