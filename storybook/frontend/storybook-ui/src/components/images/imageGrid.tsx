// ImageGrid.tsx
import React, { useEffect, useState } from "react";
import { Card, Image, Spinner } from "@heroui/react";
import { useDisclosure } from "@heroui/react";
import { useAxios } from '@/hooks/axiosContext';
import { downloadImageById } from "@/apis/imageController";
import ImageModal from "@/components/images/imageModal";

type ImageProps = {
  id: string; // Image ID (required)
  name?: string; // Display name (optional)
};

type ImageGridProps = {
  images: ImageProps[];
  isLoading?: boolean;
  onImageDelete?: (imageId: string) => void;
  customActions?: (image: ImageProps) => React.ReactNode; // For custom modal actions
  compact?: boolean;
};

const ImageGrid: React.FC<ImageGridProps> = ({
  images,
  isLoading = false,
  onImageDelete,
  customActions,
  compact = false
}) => {
  const { axiosInstance } = useAxios();
  const [thumbnails, setThumbnails] = useState<{ [imageId: string]: string }>({});
  const [selectedImage, setSelectedImage] = useState<ImageProps | null>(null);
  const { isOpen, onOpen, onClose } = useDisclosure();

  const fetchThumbnail = async (imageId: string) => {
    try {
      const response = await downloadImageById(axiosInstance, imageId);
      const reader = new FileReader();
      reader.onloadend = () => {
        setThumbnails((prev) => ({ ...prev, [imageId]: reader.result as string }));
      };
      reader.readAsDataURL(response);
    } catch (error) {
      console.error('Error fetching thumbnail:', error);
    }
  };

  useEffect(() => {
    images.forEach((image) => {
      if (image.id && !thumbnails[image.id]) {
        fetchThumbnail(image.id);
      }
    });
  }, [images]);

  const handleCardClick = (image: ImageProps) => {
    setSelectedImage(image);
    onOpen();
  };

  const handleImageDelete = (imageId: string) => {
    onImageDelete?.(imageId);
  };

  return (
    <>
      <div className={compact ? "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3" : "grid md:grid-cols-4 sm:grid-cols-1 md:gap-4 sm:gap-1"}>
        {isLoading ? (
          <div className="col-span-full flex justify-center items-center">
            <Spinner size="md" />
          </div>
        ) : (
          images.map((image) => (
            <Card
              key={image.id}
              className="border-none mb-3"
              isPressable
              onPress={() => handleCardClick(image)}
              radius="lg"
              >
              <Image
                src={thumbnails[image.id]}
                className="object-cover"
                alt={image.name || 'Image'}
              />
            </Card>
          ))
        )}
      </div>
      {selectedImage && (
        <ImageModal
          isOpen={isOpen}
          onClose={onClose}
          imageSrc={thumbnails[selectedImage.id]}
          imageName={selectedImage.name || 'Image'}
          imageId={selectedImage.id}
          onImageDelete={handleImageDelete}
          customActions={customActions ? () => customActions(selectedImage) : undefined}
        />
      )}
    </>
  );
};

export default ImageGrid;
