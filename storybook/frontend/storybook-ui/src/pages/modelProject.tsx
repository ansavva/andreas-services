// ModelProjectPage.tsx
import React, { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Spinner } from "@heroui/react";

import { exists } from "@/apis/modelController";
import { getModelProjectById } from "@/apis/modelProjectController";
import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";

import DefaultLayout from "@/layouts/default";
import Stepper from "@/components/common/stepper";
import SubjectSetupStep from "@/components/steps/subjectSetupStep";
import ImageUploadStep from "@/components/steps/imageUploadStep";
import GenerateImageStep from "@/components/steps/generateImageStep";
import ErrorDisplay from "@/components/common/errorDisplay";
import { getErrorMessage, logError } from "@/utils/errorHandling";

const ModelProjectPage: React.FC = () => {
  const { axiosInstance } = useAxios();
  const { project_id } = useParams();
  const navigate = useNavigate();
  const { showError } = useToast();

  const [project, setProject] = useState<any>(null);
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Ensure project_id is a valid string
  if (!project_id) {
    throw new Error("Project ID is required");
  }

  useEffect(() => {
    if (project_id && project_id !== "new") {
      loadProjectData();
    } else if (project_id === "new") {
      // New project - start at Subject Setup step
      setLoading(false);
      setCurrentStep(0);
    }
  }, [project_id]);

  const loadProjectData = async () => {
    try {
      setLoading(true);

      // Load model project
      const projectData = await getModelProjectById(axiosInstance, project_id!);
      setProject(projectData);

      // Determine current step based on model existence and project status
      const modelExistsResponse = await exists(axiosInstance, project_id!);
      if (modelExistsResponse.model_found || projectData.status === "READY") {
        setCurrentStep(2); // Generate Images step
      } else {
        // Check if project has been created (has images or is in training)
        setCurrentStep(1); // Image Upload & Training step
      }
    } catch (error: any) {
      logError("Load project data", error);

      // If project doesn't exist (404), show not found error
      if (error.response?.status === 404) {
        setError("Project not found. It may have been deleted.");
      } else {
        setError(
          getErrorMessage(
            error,
            "Failed to load project. Please check your connection and try again."
          )
        );
      }
    } finally {
      setLoading(false);
    }
  };

  const handleProjectCreated = (newProject: any) => {
    setProject(newProject);
    // Update URL to reflect the actual project ID
    navigate(`/model-project/${newProject.id}`, { replace: true });
  };

  const handleSubjectSetupComplete = () => {
    setCurrentStep(1); // Move to Image Upload step
  };

  const handleTrainingComplete = () => {
    setCurrentStep(2); // Move to Generate Images step
  };

  const steps = [
    { title: "Subject Setup", description: "Enter subject information" },
    { title: "Training", description: "Upload images and train your model" },
    { title: "Generate Images", description: "Create images with your trained model" },
  ];

  if (loading) {
    return (
      <DefaultLayout>
        <div className="flex justify-center items-center h-screen">
          <Spinner size="lg" />
        </div>
      </DefaultLayout>
    );
  }

  if (error) {
    const isNotFound = error.includes("not found");
    return (
      <DefaultLayout>
        <div className="container mx-auto px-4">
          <ErrorDisplay
            title={isNotFound ? "Project Not Found" : "Error Loading Project"}
            message={error}
            onRetry={() => {
              if (isNotFound) {
                navigate("/projects");
              } else {
                setError(null);
                loadProjectData();
              }
            }}
            retryText={isNotFound ? "Go to Projects" : "Retry"}
          />
        </div>
      </DefaultLayout>
    );
  }

  return (
    <DefaultLayout>
      <div className="container mx-auto px-4">
        <h1 className="text-5xl font-extrabold leading-none mb-4">
          {project ? project.name : project_id === "new" ? "New Model Project" : "Loading..."}
        </h1>
        {project && project.subject_name && (
          <p className="text-lg mb-4">Subject: {project.subject_name}</p>
        )}

        <div className="mb-8">
          <Stepper steps={steps} currentStep={currentStep} />
        </div>

        <div className="mt-8">
          {currentStep === 0 && (
            <SubjectSetupStep
              projectId={project_id}
              project={project}
              onProjectCreated={handleProjectCreated}
              onComplete={handleSubjectSetupComplete}
            />
          )}

          {currentStep === 1 && (
            <div>
              {project_id !== "new" && (
                <button
                  onClick={() => setCurrentStep(0)}
                  className="mb-4 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
                >
                  ← Back to Subject Setup
                </button>
              )}
              <ImageUploadStep
                projectId={project?.id || project_id}
                project={project}
                onTrainingComplete={handleTrainingComplete}
              />
            </div>
          )}

          {currentStep === 2 && (
            <div>
              <button
                onClick={() => setCurrentStep(1)}
                className="mb-4 text-blue-600 hover:text-blue-800 dark:text-blue-400 dark:hover:text-blue-300"
              >
                ← Back to Training
              </button>
              <GenerateImageStep projectId={project?.id || project_id} />
            </div>
          )}
        </div>
      </div>
    </DefaultLayout>
  );
};

export default ModelProjectPage;
