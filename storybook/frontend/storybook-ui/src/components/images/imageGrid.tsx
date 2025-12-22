// ImageGrid.tsx
import React, { useEffect, useState, useRef, useMemo } from "react";
import { Card, Image, Spinner, Button } from "@heroui/react";
import { useDisclosure } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faTrash,
  faCheck,
  faTriangleExclamation,
} from "@fortawesome/free-solid-svg-icons";

import { useAxios } from "@/hooks/axiosContext";
import { downloadImageById } from "@/apis/imageController";
import ImageModal from "@/components/images/imageModal";

type ImageItem = {
  id?: string;
  name?: string;
  src?: string;
};

type ImageGridProps = {
  images: ImageItem[];
  isLoading?: boolean;
  onImageDelete?: (imageId: string, image?: ImageItem) => void;
  customActions?: (image: ImageItem) => React.ReactNode;
  showDeleteButton?: boolean;
  thumbnailWidth?: number;
  thumbnailHeight?: number;
  className?: string;
  showModal?: boolean;
  selectable?: boolean;
  selectedIds?: string[];
  onImageSelect?: (
    imageId: string,
    isSelected: boolean,
    image?: ImageItem,
  ) => void;
};

const DEFAULT_CONTAINER_CLASSES =
  "flex gap-3 overflow-x-auto whitespace-nowrap py-1";

const ImageGrid: React.FC<ImageGridProps> = ({
  images,
  isLoading = false,
  onImageDelete,
  customActions,
  showDeleteButton = false,
  thumbnailWidth,
  thumbnailHeight,
  className,
  showModal = true,
  selectable = false,
  selectedIds = [],
  onImageSelect,
}) => {
  const { axiosInstance } = useAxios();
  const [thumbnails, setThumbnails] = useState<Record<string, string>>({});
  const thumbnailsRef = useRef<Record<string, string>>({});
  const [selectedImage, setSelectedImage] = useState<{
    image: ImageItem;
    key: string;
  } | null>(null);
  const { isOpen, onOpen, onClose } = useDisclosure();
  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);

  useEffect(() => {
    thumbnailsRef.current = thumbnails;
  }, [thumbnails]);

  const getImageKey = (image: ImageItem, index: number) =>
    image.id || (image.src ? `${image.src}-${index}` : `image-${index}`);

  const fetchThumbnail = async (imageId: string, key: string) => {
    try {
      const response = await downloadImageById(axiosInstance, imageId);
      const reader = new FileReader();

      reader.onloadend = () => {
        setThumbnails((prev) => ({
          ...prev,
          [key]: reader.result as string,
        }));
      };
      reader.readAsDataURL(response);
    } catch (error) {
      console.error("Error fetching thumbnail:", error);
      setThumbnails((prev) => ({
        ...prev,
        [key]: "__ERROR__",
      }));
    }
  };

  useEffect(() => {
    images.forEach((image, index) => {
      const key = getImageKey(image, index);

      if (!key) return;

      if (image.src) {
        setThumbnails((prev) =>
          prev[key] ? prev : { ...prev, [key]: image.src as string },
        );
      } else if (image.id && !thumbnailsRef.current[key]) {
        fetchThumbnail(image.id, key);
      }
    });
  }, [images, axiosInstance]);

  const handleSelectToggle = (image: ImageItem, identifier: string) => {
    if (!selectable || !identifier) return;
    const currentlySelected = selectedIdSet.has(identifier);

    onImageSelect?.(identifier, !currentlySelected, image);
  };

  const handleCardClick = (image: ImageItem, key: string) => {
    const identifier = image.id || key;

    if (selectable) {
      handleSelectToggle(image, identifier);
      if (!showModal) {
        return;
      }
    }
    if (showModal && image.id) {
      setSelectedImage({ image, key });
      onOpen();
    }
  };

  const handleImageDelete = (image: ImageItem, key: string) => {
    onImageDelete?.(image.id || key, image);
  };

  const containerClasses = className ? className : DEFAULT_CONTAINER_CLASSES;

  return (
    <>
      <div className={containerClasses}>
        {isLoading ? (
          <div className="w-full flex justify-center items-center py-4">
            <Spinner size="md" />
          </div>
        ) : (
          images.map((image, index) => {
            const key = getImageKey(image, index);
            const thumbnailSrc = thumbnails[key];
            const isErrorThumbnail = thumbnailSrc === "__ERROR__";
            const identifier = image.id || key;
            const isSelected =
              selectable && identifier ? selectedIdSet.has(identifier) : false;
            const cardStyle =
              thumbnailWidth || thumbnailHeight
                ? {
                    ...(thumbnailWidth ? { width: thumbnailWidth } : {}),
                    ...(thumbnailHeight ? { height: thumbnailHeight } : {}),
                  }
                : undefined;

            return (
              <Card
                key={key}
                className={`border-0 relative overflow-hidden inline-flex flex-none ${showModal && image.id ? "cursor-pointer" : ""} ${isSelected ? "ring-2 ring-primary" : ""}`}
                isPressable={selectable || (showModal && !!image.id)}
                radius="lg"
                style={cardStyle}
                onPress={() => handleCardClick(image, key)}
              >
                {thumbnailSrc && !isErrorThumbnail ? (
                  <Image
                    alt={image.name || "Image"}
                    className="object-cover w-full h-full"
                    src={thumbnailSrc}
                  />
                ) : (
                  <div className="w-full h-full flex items-center justify-center bg-gray-200 dark:bg-gray-700">
                    {isErrorThumbnail ? (
                      <FontAwesomeIcon
                        className="text-danger text-xl"
                        icon={faTriangleExclamation}
                      />
                    ) : (
                      <Spinner size="sm" />
                    )}
                  </div>
                )}
                {selectable && isSelected && (
                  <div className="absolute top-2 left-2 bg-primary text-white rounded-full w-6 h-6 flex items-center justify-center text-xs z-10">
                    <FontAwesomeIcon icon={faCheck} />
                  </div>
                )}
                {showDeleteButton && (
                  <Button
                    isIconOnly
                    className="absolute top-2 right-2 z-10"
                    color="danger"
                    size="sm"
                    variant="light"
                    onPress={() => handleImageDelete(image, key)}
                  >
                    <FontAwesomeIcon icon={faTrash} />
                  </Button>
                )}
              </Card>
            );
          })
        )}
      </div>
      {selectedImage && (
        <ImageModal
          customActions={
            customActions ? () => customActions(selectedImage.image) : undefined
          }
          imageId={selectedImage.image.id as string}
          imageName={selectedImage.image.name || "Image"}
          imageSrc={thumbnails[selectedImage.key]}
          isOpen={isOpen}
          showDeleteButton={showDeleteButton}
          onClose={() => {
            setSelectedImage(null);
            onClose();
          }}
          onImageDelete={
            showDeleteButton
              ? () => {
                  handleImageDelete(selectedImage.image, selectedImage.key);
                  setSelectedImage(null);
                  onClose();
                }
              : undefined
          }
        />
      )}
    </>
  );
};

export default ImageGrid;
