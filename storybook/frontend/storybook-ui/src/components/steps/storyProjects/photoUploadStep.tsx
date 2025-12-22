import React, { useRef, useState } from "react";
import { Button, Card, CardBody, Progress } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faUpload } from "@fortawesome/free-solid-svg-icons";

import { useAxios } from "@/hooks/axiosContext";
import { uploadImage, deleteImage } from "@/apis/imageController";
import ImageGrid from "@/components/images/imageGrid";

type PhotoFile = {
  id: string; // Image ID
  name?: string; // Display name
};

type PhotoUploadStepProps = {
  projectId: string;
  onComplete: (photoIds: string[]) => void;
  onBack: () => void;
  loading: boolean;
  minPhotos?: number;
  maxPhotos?: number;
};

const PhotoUploadStep: React.FC<PhotoUploadStepProps> = ({
  projectId,
  onComplete,
  onBack,
  loading,
  minPhotos = 1,
  maxPhotos = 10,
}) => {
  const { axiosInstance } = useAxios();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [photos, setPhotos] = useState<PhotoFile[]>([]);
  const [error, setError] = useState<string>("");
  const [isUploading, setIsUploading] = useState(false);

  const allowedFileTypes = [
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/heic",
    "image/heif",
  ];
  const maxFileSize = 10 * 1024 * 1024; // 10MB

  const handleFileSelect = () => {
    fileInputRef.current?.click();
  };

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;

    if (!files) return;

    setError("");

    const filesToUpload: File[] = [];
    let errorMsg = "";

    // Check if adding these files would exceed max
    if (photos.length + files.length > maxPhotos) {
      setError(`You can only upload up to ${maxPhotos} photos`);

      return;
    }

    for (let i = 0; i < files.length; i++) {
      const file = files[i];

      // Validate file type
      if (!allowedFileTypes.includes(file.type)) {
        errorMsg = `File ${file.name} is not a valid image type (jpg, png, webp, heic)`;
        continue;
      }

      // Validate file size
      if (file.size > maxFileSize) {
        errorMsg = `File ${file.name} is too large (max 10MB)`;
        continue;
      }

      filesToUpload.push(file);
    }

    if (errorMsg) {
      setError(errorMsg);
    }

    if (filesToUpload.length === 0) {
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }

      return;
    }

    // Upload all files at once
    setIsUploading(true);
    try {
      const result = await uploadImage(
        axiosInstance,
        projectId,
        "child_photos",
        filesToUpload,
      );

      // Add uploaded images to photos array
      const newPhotos: PhotoFile[] = result.images.map(
        (img: any, idx: number) => ({
          id: img.id,
          name: filesToUpload[idx].name,
        }),
      );

      setPhotos((prev) => [...prev, ...newPhotos]);
    } catch (error) {
      console.error("Error uploading photos:", error);
      setError("Failed to upload photos. Please try again.");
    } finally {
      setIsUploading(false);
      // Reset input
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleRemovePhoto = async (imageId: string) => {
    try {
      await deleteImage(axiosInstance, imageId);
      // Remove from local state
      setPhotos((prev) => prev.filter((p) => p.id !== imageId));
      setError("");
    } catch (error) {
      console.error("Error deleting photo from server:", error);
      setError("Failed to delete photo. Please try again.");
    }
  };

  const handleContinue = () => {
    if (photos.length < minPhotos) {
      setError(
        `Please upload at least ${minPhotos} photo${minPhotos > 1 ? "s" : ""}`,
      );

      return;
    }

    const photoIds = photos.map((p) => p.id);

    onComplete(photoIds);
  };

  const uploadedCount = photos.length;

  return (
    <div className="max-w-4xl mx-auto">
      <h3 className="text-2xl font-bold mb-2">Upload Photos</h3>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Upload {minPhotos}-{maxPhotos} clear photos of your child. These will be
        used to create a personalized character in the story.
      </p>

      <Card className="mb-6">
        <CardBody>
          <div className="mb-4">
            <h4 className="font-semibold mb-2">Photo Tips:</h4>
            <ul className="text-sm text-gray-600 dark:text-gray-400 list-disc list-inside space-y-1">
              <li>Use clear, well-lit photos showing your child's face</li>
              <li>Include photos from different angles</li>
              <li>Avoid photos with heavy filters or face paint</li>
              <li>Close-up portraits work best</li>
              <li>Photos are uploaded and converted automatically</li>
            </ul>
          </div>

          <input
            ref={fileInputRef}
            multiple
            accept={allowedFileTypes.join(",")}
            className="hidden"
            type="file"
            onChange={handleFileChange}
          />

          {photos.length < maxPhotos && (
            <Button
              fullWidth
              color="primary"
              isDisabled={isUploading}
              isLoading={isUploading}
              startContent={<FontAwesomeIcon icon={faUpload} />}
              variant="flat"
              onPress={handleFileSelect}
            >
              Select Photos ({uploadedCount}/{maxPhotos})
            </Button>
          )}

          {error && <p className="text-danger text-sm mt-2">{error}</p>}

          <Progress
            className="mt-4"
            color={uploadedCount >= minPhotos ? "success" : "default"}
            value={(uploadedCount / maxPhotos) * 100}
          />
          <p className="text-sm text-gray-500 mt-1">
            {uploadedCount} of {maxPhotos} photos uploaded
            {uploadedCount < minPhotos && ` (minimum ${minPhotos})`}
            {isUploading && ` - uploading...`}
          </p>
        </CardBody>
      </Card>

      {photos.length > 0 && (
        <div className="mb-6">
          <ImageGrid images={photos} onImageDelete={handleRemovePhoto} />
        </div>
      )}

      <div className="flex justify-between">
        <Button
          isDisabled={loading || isUploading}
          variant="flat"
          onPress={onBack}
        >
          Back
        </Button>
        <Button
          color="primary"
          isDisabled={loading || uploadedCount < minPhotos || isUploading}
          isLoading={loading}
          size="lg"
          onPress={handleContinue}
        >
          Continue to Character Generation
        </Button>
      </div>
    </div>
  );
};

export default PhotoUploadStep;
