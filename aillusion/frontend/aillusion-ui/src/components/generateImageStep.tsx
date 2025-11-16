// GenerateImageStep.tsx
import React, { useState, useEffect } from "react";
import { Button, Textarea } from "@nextui-org/react";
import { useAxios } from '@/hooks/axiosContext'
import { generate } from "@/apis/modelController";
import { listImages } from "@/apis/imageController";
import ImageGrid from "@/components/imageGrid";

type ImageProps = {
  key: string;
  name: string;
};

type GenerateImageStepProps = {
  projectId: string;
};

const GenerateImageStep: React.FC<GenerateImageStepProps> = ({ projectId }) => {
  const { axiosInstance } = useAxios();
  const [images, setImages] = useState<ImageProps[]>([]);
  const [prompt, setPrompt] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [loadingImages, setLoadingImages] = useState(false);

  const fetchImages = async () => {
    setLoading(true);
    setLoadingImages(true);
    try {
      const response = await listImages(axiosInstance, projectId, "generated_images");
      setImages(response.files);
    } finally { 
      setLoading(false);
      setLoadingImages(false);
    }
  };

  const handleGenerate = async () => {
    if (!prompt.trim()) {
      return;
    }
    setLoading(true);
    try {
      const file = await generate(axiosInstance, prompt, projectId);
      setImages(prevImages => [file, ...prevImages]);
    } finally {
      setLoading(false);
    }
  };

  const handleImageDelete = (key: string) => {
    setImages((prevImages) => prevImages.filter((img) => img.key !== key));
  };

  useEffect(() => {
    fetchImages();
  }, []);

  return (
    <div className="mt-6">
      <h3 className="text-xl font-bold mb-2">Generate Image</h3>
      <Textarea
        label="Enter your prompt"
        value={prompt}
        onChange={(e) => setPrompt(e.target.value)}
        rows={4}
        placeholder="Type your prompt here..."
        description="Enter any prompot your want with the subject you see above. For example: (andreas being a giant queer)"
      />
      <Button 
        color="primary" 
        onPress={handleGenerate} 
        className="mt-4" 
        isLoading={loading} 
        disabled={!prompt.trim()}
        isDisabled={!prompt.trim()}
      >
        Generate Image
      </Button>
      <div className="mt-4">
        <ImageGrid 
          projectId={projectId} 
          directory="generated_images" 
          images={images}
          isLoading={loadingImages}
          onImageDelete={handleImageDelete}
        />
      </div>
    </div>
  );
};

export default GenerateImageStep;