import React, { useRef, useState, useEffect } from "react";
import { Button, Input } from "@nextui-org/react";
import { uploadImage, listImages } from "../apis/imageController";
import { useAxios } from '@/hooks/axiosContext';
import ImageGrid from "./imageGrid";

type ImageFile = {
  key: string;
  name: string;
};

type ImageUploadStepProps = {
  projectId: string;
  onTrainClick: () => void;
  loading: boolean
};

const ImageUploadStep: React.FC<ImageUploadStepProps> = ({ projectId, onTrainClick, loading }) => {
  const { axiosInstance } = useAxios();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [images, setImages] = useState<ImageFile[]>([]);
  const [isLoading, setIsLoading] = useState(false);

  // Define allowed file types (image formats)
  const allowedFileTypes = ["image/jpeg", "image/png"];

  const fetchImages = async () => {
    setIsLoading(true);
    try {
      const response = await listImages(axiosInstance, projectId, "uploaded_images");
      setImages(response.files);
    } catch (error) {
      console.error('Error fetching images:', error);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchImages();
  }, [projectId]);

  const handleFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files) {
      const selectedFiles = Array.from(e.target.files);
      // Trigger the upload for selected files
      await handleUpload(selectedFiles);

      // Clear selected files
      if (fileInputRef.current) {
        fileInputRef.current.value = ""; // Reset the input value to clear selected files
      }
    }
  };

  const handleUpload = async (filesToUpload: File[]) => {
    setIsLoading(true);
    try {
      if (filesToUpload.length === 0) return;
      await uploadImage(axiosInstance, projectId, "uploaded_images", filesToUpload);
      // Refresh the images list after upload
      await fetchImages();
    } catch (error) {
      console.error('Error uploading images:', error);
    } finally {
      setIsLoading(false);
    }
  };

  const handleImageDelete = async (key: string) => {
    setImages(prevImages => prevImages.filter(img => img.key !== key));
  };

  return (
    <div>
      <h3 className="text-xl font-bold mb-2">Upload Images</h3>
      <Input
        ref={fileInputRef}
        type="file"
        multiple
        accept={allowedFileTypes.join(",")}
        onChange={handleFileChange}
        className="mb-4"
      />
      <ImageGrid 
        projectId={projectId} 
        directory="uploaded_images" 
        images={images}
        isLoading={isLoading}
        onImageDelete={handleImageDelete}
      />
      <Button 
        color="primary" 
        onPress={onTrainClick} 
        className="mt-4" 
        isLoading={loading}
        isDisabled={images.length === 0}
      >
        Start Training
      </Button>
    </div>
  );
};

export default ImageUploadStep;
