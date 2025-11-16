// ImageModal.tsx
import React from "react";
import { Modal, ModalContent, ModalBody, ModalFooter, Button, Image } from "@nextui-org/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faDownload, faTrash } from "@fortawesome/free-solid-svg-icons";
import { downloadImage, deleteImage } from "../apis/imageController";
import { useAxios } from '@/hooks/axiosContext';

type ImageModalProps = {
  isOpen: boolean;
  onClose: () => void;
  imageSrc: string;
  imageName: string;
  projectId: string;
  directory: string;
  imageKey: string;
  onImageDelete: (key: string) => void; // Callback to refresh the grid after deletion
};

const ImageModal: React.FC<ImageModalProps> = ({ 
  isOpen, 
  onClose, 
  imageSrc, 
  imageName, 
  projectId, 
  directory, 
  imageKey,
  onImageDelete 
}) => {
  const { axiosInstance } = useAxios();

  const handleDownload = async () => {
    try {
      const fileBlob = await downloadImage(axiosInstance, projectId, directory, imageKey);
      const downloadUrl = window.URL.createObjectURL(new Blob([fileBlob]));
      const link = document.createElement("a");
      link.href = downloadUrl;
      link.setAttribute("download", imageKey);
      document.body.appendChild(link);
      link.click();
    } catch (error) {
      console.error("Error downloading image:", error);
    }
  };

  const handleDelete = async () => {
    try {
      onImageDelete(imageKey); // Trigger a refresh in the grid
      onClose(); // Close the modal after deletion
      await deleteImage(axiosInstance, projectId, directory, imageKey);
    } catch (error) {
      console.error("Error deleting image:", error);
    }
  };


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
          {/* Left-aligned download and delete buttons */}
          <div className="flex gap-2">
            <Button
              variant="light"
              isIconOnly
              onPress={handleDownload}
              aria-label="Download"
            >
              <FontAwesomeIcon icon={faDownload} />
            </Button>
            <Button
              variant="light"
              isIconOnly
              onPress={handleDelete}
              aria-label="Delete"
            >
              <FontAwesomeIcon icon={faTrash} />
            </Button>
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