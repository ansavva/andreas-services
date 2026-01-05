// ImageModal.tsx
import React from "react";
import {
  Modal,
  ModalContent,
  ModalBody,
  ModalFooter,
  Button,
  Image,
} from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faDownload, faTrash } from "@fortawesome/free-solid-svg-icons";

import { fetchImageDownloadUrl, deleteImage } from "@/apis/imageController";
import { useAxios } from "@/hooks/axiosContext";

type ImageModalProps = {
  isOpen: boolean;
  onClose: () => void;
  imageSrc: string;
  imageName: string;
  imageId: string;
  onImageDelete?: (imageId: string) => void;
  customActions?: () => React.ReactNode; // Custom action buttons
  showDeleteButton?: boolean;
};

const ImageModal: React.FC<ImageModalProps> = ({
  isOpen,
  onClose,
  imageSrc,
  imageName,
  imageId,
  onImageDelete,
  customActions,
  showDeleteButton = true,
}) => {
  const { axiosInstance } = useAxios();

  const handleDownload = async () => {
    try {
      const url = await fetchImageDownloadUrl(axiosInstance, imageId);
      const link = document.createElement("a");
      link.href = url;
      link.setAttribute("download", imageName || `${imageId}.png`);
      document.body.appendChild(link);
      link.click();
      link.remove();
    } catch (error) {
      console.error("Error downloading image:", error);
    }
  };

  const handleDelete = async () => {
    if (!onImageDelete) return;

    try {
      onImageDelete(imageId); // Trigger a refresh in the grid
      onClose(); // Close the modal after deletion
      await deleteImage(axiosInstance, imageId);
    } catch (error) {
      console.error("Error deleting image:", error);
    }
  };

  const showDefaultActions = !customActions;

  return (
    <Modal isOpen={isOpen} onOpenChange={onClose}>
      <ModalContent>
        <ModalBody className="p-0 m-0">
          <Image
            alt={imageName}
            className="object-cover w-full h-auto rounded-none"
            src={imageSrc}
          />
        </ModalBody>
        <ModalFooter className="flex justify-between w-full">
          {/* Left-aligned action buttons */}
          <div className="flex gap-2">
            {!showDefaultActions && customActions ? (
              customActions()
            ) : (
              <>
                <Button
                  isIconOnly
                  aria-label="Download"
                  variant="light"
                  onPress={handleDownload}
                >
                  <FontAwesomeIcon icon={faDownload} />
                </Button>
                {showDeleteButton && onImageDelete && (
                  <Button
                    isIconOnly
                    aria-label="Delete"
                    variant="light"
                    onPress={handleDelete}
                  >
                    <FontAwesomeIcon icon={faTrash} />
                  </Button>
                )}
              </>
            )}
          </div>
          {/* Right-aligned close button */}
          <Button aria-label="Close" variant="light" onPress={onClose}>
            Close
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default ImageModal;
