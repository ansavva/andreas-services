import { useEffect, useState, useMemo } from 'react';
import { Button, Card, CardBody, Input, Modal, ModalContent, ModalBody, ModalFooter, ModalHeader, useDisclosure } from '@nextui-org/react';
import { useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlus } from "@fortawesome/free-solid-svg-icons";

import { useAxios } from '@/hooks/axiosContext';
import { getProjects, createProject } from '../apis/projectController';
import DefaultLayout from '@/layouts/default';

const ProjectsPage = () => {
  const { axiosInstance } = useAxios();
  const navigate = useNavigate();  // Initialize useNavigate for navigation

  const { isOpen, onOpen, onOpenChange } = useDisclosure();  // Initialize modal state

  const [projects, setProjects] = useState<any[]>([]);
  const [newProjectName, setNewProjectName] = useState<string | null>(null);
  const [subjectName, setSubjectName] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const projects = await getProjects(axiosInstance);
        setProjects(projects);
      } catch (error) {
        console.error('Error fetching projects:', error);
      }
    };
    fetchProjects();
  }, []);

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
      navigate(`/project/${newProject.id}`);  // Navigate to the new project page
    } catch (error) {
      console.error('Error creating project:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleCardClick = (projectId: string) => {
    // Navigate to the project page using projectId
    navigate(`/project/${projectId}`);
  };

  return (
    <DefaultLayout>
      <div className="flex justify-between items-center mb-4">
        <h1 className="text-5xl font-extrabold leading-none">Projects</h1>
        <Button isIconOnly onPress={onOpen} aria-label="Add Project">
          <FontAwesomeIcon icon={faPlus} />
        </Button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        {projects.map((project) => (
          <Card key={project.id} isPressable onPress={() => handleCardClick(project.id)} className="cursor-pointer">
            <CardBody>
              <h4>{project.name}</h4>
            </CardBody>
          </Card>
        ))}
      </div>

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