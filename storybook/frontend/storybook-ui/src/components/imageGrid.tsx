// ImageGrid.tsx
import React, { useEffect, useState } from "react";
import { Card, Image, Spinner } from "@nextui-org/react";
import { useDisclosure } from "@nextui-org/react";
import { useAxios } from '@/hooks/axiosContext';
import { downloadImage } from "../apis/imageController";
import ImageModal from "./imageModal";

type ImageProps = {
  key: string;
  name: string;
};

type ImageGridProps = {
  projectId: string;
  directory: string;
  images: ImageProps[];
  isLoading?: boolean;
  onImageDelete?: (key: string) => void;
};

const ImageGrid: React.FC<ImageGridProps> = ({ 
  projectId, 
  directory, 
  images, 
  isLoading = false,
  onImageDelete 
}) => {
  const { axiosInstance } = useAxios();
  const [thumbnails, setThumbnails] = useState<{ [key: string]: string }>({});
  const [selectedImage, setSelectedImage] = useState<ImageProps | null>(null);
  const { isOpen, onOpen, onClose } = useDisclosure();

  const fetchThumbnail = async (key: string) => {
    const response = await downloadImage(axiosInstance, projectId, directory, key);
    const reader = new FileReader();
    reader.onloadend = () => {
      setThumbnails((prev) => ({ ...prev, [key]: reader.result as string }));
    };
    reader.readAsDataURL(response);
  };

  useEffect(() => {
    images.forEach((image) => {
      if (!thumbnails[image.key]) {
        fetchThumbnail(image.key);
      }
    });
  }, [images]);

  const handleCardClick = (image: ImageProps) => {
    setSelectedImage(image);
    onOpen();
  };

  const handleImageDelete = (key: string) => {
    onImageDelete?.(key);
  };

  return (
    <>
      <div className="grid md:grid-cols-4 sm:grid-cols-1 md:gap-4 sm:gap-1">
        {isLoading ? (
          <div className="col-span-4 flex justify-center items-center">
            <Spinner size="md" />
          </div>
        ) : (
          images.map((image) => (
            <Card 
              key={image.key} 
              className="border-none mb-3" 
              isPressable 
              onPress={() => handleCardClick(image)} 
              radius="lg"
            >
              <Image
                src={thumbnails[image.key]}
                className="object-cover"
                alt={image.name}
              />
            </Card>
          ))
        )}
      </div>
      {selectedImage && (
        <ImageModal
          isOpen={isOpen}
          onClose={onClose}
          imageSrc={thumbnails[selectedImage.key]}
          imageName={selectedImage.name}
          projectId={projectId}
          directory={directory}
          imageKey={selectedImage.key}
          onImageDelete={handleImageDelete}
        />
      )}
    </>
  );
};

export default ImageGrid;