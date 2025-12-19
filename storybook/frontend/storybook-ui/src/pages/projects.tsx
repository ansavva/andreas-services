import { useEffect, useState, useMemo } from 'react';
import { Button, Card, CardBody, Input, Modal, ModalContent, ModalBody, ModalFooter, ModalHeader, useDisclosure, Tabs, Tab, Chip } from '@heroui/react';
import { useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlus, faBook } from "@fortawesome/free-solid-svg-icons";

import { useAxios } from '@/hooks/axiosContext';
import { getProjects, createProject } from '../apis/projectController';
import { getStoryProjects, createStoryProject } from '../apis/storyProjectController';
import DefaultLayout from '@/layouts/default';
import { getErrorMessage, logError } from '@/utils/errorHandling';
import { useToast } from '@/hooks/useToast';

const ProjectsPage = () => {
  const { axiosInstance } = useAxios();
  const navigate = useNavigate();  // Initialize useNavigate for navigation
  const { showError, showSuccess } = useToast();

  const { isOpen, onOpen, onOpenChange } = useDisclosure();  // Initialize modal state

  const [activeTab, setActiveTab] = useState('training');
  const [projects, setProjects] = useState<any[]>([]);
  const [storyProjects, setStoryProjects] = useState<any[]>([]);
  const [newProjectName, setNewProjectName] = useState<string | null>(null);
  const [subjectName, setSubjectName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const [trainingProjects, storyProjectsList] = await Promise.all([
          getProjects(axiosInstance),
          getStoryProjects(axiosInstance),
        ]);
        setProjects(trainingProjects);
        setStoryProjects(storyProjectsList);
      } catch (error: any) {
        logError('Fetch projects', error);
        showError(getErrorMessage(error, 'Failed to load projects'));
      }
    };
    fetchProjects();
  }, [axiosInstance, showError]);

  // Validation checks for empty strings only, treating null as valid (initial state)
  const isProjectNameInvalid = useMemo(() => newProjectName === '', [newProjectName]);
  const isSubjectNameInvalid = useMemo(() => subjectName === '', [subjectName]);

  const handleCreateProject = async () => {
    if (newProjectName == null || subjectName == null || isProjectNameInvalid || isSubjectNameInvalid) {
      if (newProjectName == null || isProjectNameInvalid) {
        setNewProjectName('');
      }
      if (subjectName == null || isSubjectNameInvalid) {
        setSubjectName('');
      }
      return;
    }
    setLoading(true);

    try {
      const newProject = await createProject(axiosInstance, newProjectName as string, subjectName as string);
      setProjects([...projects, newProject]);
      setNewProjectName('');
      setSubjectName('');
      showSuccess('Project created successfully!');
      navigate(`/project/${newProject.id}`);  // Navigate to the new project page
    } catch (error: any) {
      logError('Create project', error);
      showError(getErrorMessage(error, 'Failed to create project'));
    } finally {
      setLoading(false);
    }
  };

  const handleCreateStoryProject = () => {
    // Navigate to kid setup page (project will be created after kid setup is complete)
    navigate('/story-project/new');
  };

  const handleCardClick = (projectId: string) => {
    // Navigate to the project page using projectId
    navigate(`/project/${projectId}`);
  };

  const handleStoryCardClick = (projectId: string) => {
    navigate(`/story-project/${projectId}`);
  };

  const getStatusLabel = (status: string) => {
    const statusLabels: { [key: string]: { label: string; color: any } } = {
      'DRAFT_SETUP': { label: 'Setup', color: 'default' },
      'CHARACTER_PREVIEW': { label: 'Character', color: 'primary' },
      'CHAT': { label: 'Chatting', color: 'secondary' },
      'COMPILED': { label: 'Compiled', color: 'success' },
      'ILLUSTRATING': { label: 'Illustrating', color: 'warning' },
      'READY': { label: 'Ready', color: 'success' },
      'EXPORTED': { label: 'Exported', color: 'success' },
    };
    return statusLabels[status] || { label: status, color: 'default' };
  };

  return (
    <DefaultLayout>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-5xl font-extrabold leading-none">Projects</h1>
      </div>

      <Tabs selectedKey={activeTab} onSelectionChange={(key) => setActiveTab(key as string)} className="mb-6">
        <Tab key="training" title="Training Projects">
          <div className="flex justify-end mb-4">
            <Button onPress={onOpen} startContent={<FontAwesomeIcon icon={faPlus} />}>
              New Training Project
            </Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => (
              <Card key={project.id} isPressable onPress={() => handleCardClick(project.id)} className="cursor-pointer">
                <CardBody>
                  <h4>{project.name}</h4>
                  <p className="text-sm text-gray-500">Subject: {project.subject_name}</p>
                </CardBody>
              </Card>
            ))}
            {projects.length === 0 && (
              <p className="text-gray-500 col-span-full text-center py-8">No training projects yet. Create one to get started!</p>
            )}
          </div>
        </Tab>

        <Tab key="stories" title="Story Projects">
          <div className="flex justify-end mb-4">
            <Button color="primary" onPress={handleCreateStoryProject} startContent={<FontAwesomeIcon icon={faBook} />}>
              New Story Project
            </Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {storyProjects.map((project) => {
              const statusInfo = getStatusLabel(project.status);
              return (
                <Card key={project._id} isPressable onPress={() => handleStoryCardClick(project._id)} className="cursor-pointer">
                  <CardBody>
                    <div className="flex justify-between items-start mb-2">
                      <h4 className="flex-1">{project.name}</h4>
                      <Chip size="sm" color={statusInfo.color} variant="flat">
                        {statusInfo.label}
                      </Chip>
                    </div>
                    <p className="text-xs text-gray-500">
                      Updated: {new Date(project.updated_at).toLocaleDateString()}
                    </p>
                  </CardBody>
                </Card>
              );
            })}
            {storyProjects.length === 0 && (
              <p className="text-gray-500 col-span-full text-center py-8">No story projects yet. Create one to start writing!</p>
            )}
          </div>
        </Tab>
      </Tabs>

      {/* Modal for creating a new project */}
      <Modal isOpen={isOpen} onOpenChange={onOpenChange} isDismissable={false} isKeyboardDismissDisabled={true}>
        <ModalContent>
          {(onClose) => (
            <>
              <ModalHeader className="flex flex-col gap-1">Create New Project</ModalHeader>
              <ModalBody>
                <Input
                  label="Project Name"
                  value={newProjectName ?? ''}
                  isInvalid={isProjectNameInvalid}
                  color={isProjectNameInvalid ? "danger" : "default"}
                  errorMessage={isProjectNameInvalid ? "Project name is required" : ""}
                  onValueChange={setNewProjectName}
                  description="The name you would like to give your new project."
                />
                <Input
                  label="Subject"
                  value={subjectName ?? ''}
                  isInvalid={isSubjectNameInvalid}
                  color={isSubjectNameInvalid ? "danger" : "default"}
                  errorMessage={isSubjectNameInvalid ? "Subject is required" : ""}
                  onValueChange={setSubjectName}
                  description="The subject of your project. This is the name you will use in your prompts. (Suggestion: Your First Name)"
                />
              </ModalBody>
              <ModalFooter>
                <Button variant="light" onPress={onClose}>
                  Cancel
                </Button>
                <Button
                  color="primary"
                  onPress={handleCreateProject}
                  disabled={loading || isProjectNameInvalid || isSubjectNameInvalid}
                >
                  Create Project
                </Button>
              </ModalFooter>
            </>
          )}
        </ModalContent>
      </Modal>

    </DefaultLayout>
  );
};

export default ProjectsPage;