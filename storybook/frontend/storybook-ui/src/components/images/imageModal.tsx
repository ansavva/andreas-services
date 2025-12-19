// ImageModal.tsx
import React from "react";
import { Modal, ModalContent, ModalBody, ModalFooter, Button, Image } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faDownload, faTrash } from "@fortawesome/free-solid-svg-icons";
import { downloadImageById, deleteImage } from "@/apis/imageController";
import { useAxios } from '@/hooks/axiosContext';

type ImageModalProps = {
  isOpen: boolean;
  onClose: () => void;
  imageSrc: string;
  imageName: string;
  imageId: string;
  onImageDelete?: (imageId: string) => void;
  customActions?: () => React.ReactNode; // Custom action buttons
};

const ImageModal: React.FC<ImageModalProps> = ({
  isOpen,
  onClose,
  imageSrc,
  imageName,
  imageId,
  onImageDelete,
  customActions
}) => {
  const { axiosInstance } = useAxios();

  const handleDownload = async () => {
    try {
      const fileBlob = await downloadImageById(axiosInstance, imageId);
      const filename = `${imageId}.png`;

      const downloadUrl = window.URL.createObjectURL(new Blob([fileBlob]));
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      link.remove();
      window.URL.revokeObjectURL(downloadUrl);
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
            src={imageSrc}
            className="object-cover w-full h-auto rounded-none"
            alt={imageName}
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
                  variant="light"
                  isIconOnly
                  onPress={handleDownload}
                  aria-label="Download"
                >
                  <FontAwesomeIcon icon={faDownload} />
                </Button>
                {onImageDelete && (
                  <Button
                    variant="light"
                    isIconOnly
                    onPress={handleDelete}
                    aria-label="Delete"
                  >
                    <FontAwesomeIcon icon={faTrash} />
                  </Button>
                )}
              </>
            )}
          </div>
          {/* Right-aligned close button */}
          <Button
            variant="light"
            onPress={onClose}
            aria-label="Close"
          >
            Close
          </Button>
        </ModalFooter>
      </ModalContent>
    </Modal>
  );
};

export default ImageModal;