import { useState, useEffect } from "react";
import { useParams, useNavigate } from "react-router-dom";
import { Tabs, Tab, Spinner, Button, Modal, ModalContent, ModalHeader, ModalBody, ModalFooter, useDisclosure } from "@heroui/react";

import { exists, getTrainingRuns } from "@/apis/modelController";
import { getModelProjectById, deleteModelProject, getModelTypes } from "@/apis/modelProjectController";
import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";

import DefaultLayout from "@/layouts/default";
import SubjectSetupStep from "@/components/steps/modelProjects/subjectSetupStep";
import TrainingStep from "@/components/steps/modelProjects/trainingStep";
import GenerateImageStep from "@/components/steps/modelProjects/generateImageStep";
import ModelProjectSettingsStep from "@/components/steps/modelProjects/modelProjectSettingsStep";
import ErrorDisplay from "@/components/common/errorDisplay";
import { getErrorMessage, logError } from "@/utils/errorHandling";

export default function ModelProjectPage() {
  const { axiosInstance } = useAxios();
  const { project_id } = useParams();
  const navigate = useNavigate();
  const { showError, showSuccess } = useToast();
  const { isOpen: isDeleteOpen, onOpen: onDeleteOpen, onClose: onDeleteClose } = useDisclosure();

  const [project, setProject] = useState<any>(null);
  const [selectedTab, setSelectedTab] = useState<string>("training");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modelExists, setModelExists] = useState(false);
  const [hasSuccessfulTraining, setHasSuccessfulTraining] = useState(false);
  const [isDeleting, setIsDeleting] = useState(false);
  const [needsSubjectSetup, setNeedsSubjectSetup] = useState(false);
  const [requiresTraining, setRequiresTraining] = useState<boolean>(true);
  const [modelTypeInfo, setModelTypeInfo] = useState<any>(null);

  // Ensure project_id is valid
  if (!project_id) {
    throw new Error("Project ID is required");
  }

  useEffect(() => {
    if (project_id === "new") {
      // New project - show subject setup
      setNeedsSubjectSetup(true);
      setLoading(false);
    } else {
      loadProjectData();
    }
  }, [project_id]);

  const loadProjectData = async () => {
    try {
      setLoading(true);

      // Load model project
      const projectData = await getModelProjectById(axiosInstance, project_id!);
      setProject(projectData);

      // Fetch model types to determine if this model requires training
      const modelTypesData = await getModelTypes(axiosInstance);
      const currentModelTypeInfo = modelTypesData.modelTypes.find(
        (mt: any) => mt.id === projectData.model_type
      );
      setModelTypeInfo(currentModelTypeInfo || null);

      const needsTraining = currentModelTypeInfo?.requires_training ?? true;
      setRequiresTraining(needsTraining);

      // For generation-only models, skip training checks and go directly to generation
      if (!needsTraining) {
        setSelectedTab("generate");
        setHasSuccessfulTraining(true); // Enable generation tab
        setModelExists(true); // No model training needed
      } else {
        // For training models, check if model exists and training status
        const modelExistsResponse = await exists(axiosInstance, project_id!);
        const modelReady = modelExistsResponse.model_found || projectData.status === "READY";
        setModelExists(modelReady);

        const { hasSuccess, hasActive } = await refreshTrainingProgress(project_id!);
        if (!hasActive && (modelReady || hasSuccess)) {
          setSelectedTab("generate");
        } else if (hasActive) {
          setSelectedTab("training");
        }
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

  const refreshTrainingProgress = async (projId: string) => {
    try {
      const response = await getTrainingRuns(axiosInstance, projId);
      const runs = response.training_runs || [];
      const hasSuccess = runs.some((run: any) => run.status === "succeeded");
      const hasActive = runs.some((run: any) =>
        ["starting", "processing"].includes(run.status),
      );
      setHasSuccessfulTraining(hasSuccess);
      return { hasSuccess, hasActive };
    } catch (error) {
      logError("Get training runs", error);
      return { hasSuccess: false, hasActive: false };
    }
  };

  const handleProjectCreated = (newProject: any) => {
    setProject(newProject);
    setNeedsSubjectSetup(false);
    // Update URL to reflect the actual project ID
    navigate(`/model-project/${newProject.id}`, { replace: true });
  };

  const handleTrainingComplete = () => {
    setModelExists(true);
    setHasSuccessfulTraining(true);
    loadProjectData(); // Reload to get updated status
  };

  const handleDeleteProject = async () => {
    setIsDeleting(true);
    try {
      await deleteModelProject(axiosInstance, project_id!);
      showSuccess("Project deleted successfully");
      navigate("/projects");
    } catch (error) {
      console.error("Error deleting project:", error);
      showError("Failed to delete project");
      setIsDeleting(false);
      onDeleteClose();
    }
  };

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

  // Show subject setup for new projects
  if (needsSubjectSetup) {
    return (
      <DefaultLayout>
        <div className="container mx-auto px-4">
          <h1 className="text-5xl font-extrabold leading-none mb-6">
            New Model Project
          </h1>
          <SubjectSetupStep
            projectId={project_id}
            project={project}
            onProjectCreated={handleProjectCreated}
            onComplete={() => setNeedsSubjectSetup(false)}
          />
        </div>
      </DefaultLayout>
    );
  }

  return (
    <DefaultLayout>
      <div className="container mx-auto px-4">
        {/* Header */}
        <div className="flex justify-between items-start mb-6">
          <div>
            <h1 className="text-5xl font-extrabold leading-none mb-2">
              {project?.name || "Project"}
            </h1>
            {project?.subject_name && (
              <p className="text-lg text-gray-600 dark:text-gray-400">
                Subject: {project.subject_name}
              </p>
            )}
            {modelTypeInfo && (
              <p className="text-base text-gray-500 dark:text-gray-400 mt-1">
                Model: {modelTypeInfo.name || modelTypeInfo.id}
              </p>
            )}
          </div>
        </div>

        {/* Tabs */}
        <Tabs
          selectedKey={selectedTab}
          onSelectionChange={(key) => setSelectedTab(key as string)}
          aria-label="Project tabs"
          className="mb-6"
        >
          {/* Only show Training tab if model requires training */}
          {requiresTraining && (
            <Tab key="training" title="Training">
              <div>
                <TrainingStep
                  projectId={project?.id || project_id!}
                  onTrainingComplete={handleTrainingComplete}
                />
              </div>
            </Tab>
          )}

          <Tab
            key="generate"
            title="Generate Images"
            isDisabled={requiresTraining && !hasSuccessfulTraining}
          >
            <div>
              {(requiresTraining && modelExists) || !requiresTraining ? (
                <GenerateImageStep
                  projectId={project?.id || project_id!}
                  project={project}
                  modelTypeInfo={modelTypeInfo}
                />
              ) : (
                <div className="text-center py-12 text-gray-500 dark:text-gray-400">
                  <p>Complete training before generating images</p>
                </div>
              )}
            </div>
          </Tab>

          <Tab key="settings" title="Settings">
            <div>
              <ModelProjectSettingsStep
                project={project}
                onDeleteProject={onDeleteOpen}
                onProjectUpdated={(updated) => setProject(updated)}
              />
            </div>
          </Tab>
        </Tabs>

        {/* Delete Confirmation Modal */}
        <Modal isOpen={isDeleteOpen} onClose={onDeleteClose}>
          <ModalContent>
            <ModalHeader>Delete Project</ModalHeader>
            <ModalBody>
              <p>Are you sure you want to delete this project?</p>
              <p className="text-sm text-gray-600 dark:text-gray-400 mt-2">
                This will permanently delete:
              </p>
              <ul className="list-disc list-inside text-sm text-gray-600 dark:text-gray-400 mt-2">
                {requiresTraining && <li>All training runs and their history</li>}
                {requiresTraining && <li>All training images</li>}
                <li>All generated images</li>
                {requiresTraining && <li>The trained model on Replicate</li>}
                <li>All generation history</li>
              </ul>
              <p className="text-sm font-semibold text-red-600 dark:text-red-400 mt-4">
                This action cannot be undone.
              </p>
            </ModalBody>
            <ModalFooter>
              <Button variant="light" onPress={onDeleteClose} isDisabled={isDeleting}>
                Cancel
              </Button>
              <Button
                color="danger"
                onPress={handleDeleteProject}
                isLoading={isDeleting}
              >
                Delete Project
              </Button>
            </ModalFooter>
          </ModalContent>
        </Modal>
      </div>
    </DefaultLayout>
  );
}
