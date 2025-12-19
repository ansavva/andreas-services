// ProjectPage.tsx
import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";

import { train, training_status, exists } from "@/apis/modelController";
import { getProjectById } from "@/apis/projectController";
import { useAxios } from '@/hooks/axiosContext'

import DefaultLayout from "@/layouts/default";
import Stepper from "@/components/common/stepper";
import ImageUploadStep from "@/components/steps/imageUploadStep";
import TrainingStep from "@/components/steps/trainingStep";
import GenerateImageStep from "@/components/steps/generateImageStep";

const ProjectPage: React.FC = () => {
  const { axiosInstance } = useAxios();
  const { project_id } = useParams();

  const [project, setProject] = useState<any>(null);
  const [currentStep, setCurrentStep] = useState<number|null>(null);
  const [loading, setLoading] = useState(false);
  const [trainingStatus, setTrainingStatus] = useState<string>("pending");

  // Ensure project_id is a valid string
  if (!project_id) {
    // Handle the case where project_id is undefined, you can either show an error or redirect
    throw new Error("Project ID is required");
  }

  useEffect(() => {
    const fetchProject = async () => {
      const projectData = await getProjectById(axiosInstance, project_id);
      setProject(projectData);

      const modelExistsResponse = await exists(axiosInstance, project_id);
      if (modelExistsResponse.model_found) {
        setCurrentStep(3);
        setLoading(false);
      } else {
        setCurrentStep(1);
      }
    };
    fetchProject();
  }, [project_id]);

  const handleTrain = async () => {
    setLoading(true);
    try {
      const response = await train(axiosInstance, project_id, "uploaded_images");
      setTrainingStatus("running");
      setCurrentStep(2);
      await pollTrainingStatus(response.training_id);
    } finally {
      setLoading(false);
    }
  };

  const pollTrainingStatus = async (training_id: string) => {
    const intervalId = setInterval(async () => {
      try {
        const { status } = await training_status(axiosInstance, training_id);
        setTrainingStatus(status);
        if (status === "succeeded" || status === "failed") {
          clearInterval(intervalId);
          setCurrentStep(3);
        }
      } catch {
        clearInterval(intervalId);
        setTrainingStatus("failed");
      }
    }, 5000);
  };

  const steps = [
    { title: "Upload Images", description: "Upload images and start training" },
    { title: "Training", description: "AI model is being generated" },
    { title: "Generate Images", description: "Enter a prompt to generate images" }
  ];

  return (
    <DefaultLayout>
      <h1 className="text-5xl font-extrabold leading-none mb-4">
        {project ? project.name : "Loading..."}
      </h1>
      {project && <p className="text-lg mb-4">Subject: {project.subjectName}</p>}
      <div className="mb-5">
        <Stepper steps={steps} currentStep={currentStep ?? 1} />
      </div>
      {currentStep === 1 && (
        <ImageUploadStep
          projectId={project_id}
          onTrainClick={handleTrain}
          loading={loading}
        />
      )}
      {currentStep === 2 && (
        <TrainingStep
          trainingStatus={trainingStatus}
        />
      )}
      {currentStep === 3 && (
        <GenerateImageStep
          projectId={project_id}
        />
      )}
    </DefaultLayout>
  );
};

export default ProjectPage;