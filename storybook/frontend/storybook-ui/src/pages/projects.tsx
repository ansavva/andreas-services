import { useEffect, useState } from 'react';
import { Button, Card, CardBody, Dropdown, DropdownTrigger, DropdownMenu, DropdownItem, Chip } from '@heroui/react';
import { useNavigate } from 'react-router-dom';
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPlus, faChevronDown, faWandMagicSparkles, faBook } from "@fortawesome/free-solid-svg-icons";

import { useAxios } from '@/hooks/axiosContext';
import { getModelProjects } from '../apis/modelProjectController';
import { getStoryProjects } from '../apis/storyProjectController';
import DefaultLayout from '@/layouts/default';
import { getErrorMessage, logError } from '@/utils/errorHandling';
import { useToast } from '@/hooks/useToast';

type Project = {
  id: string;
  name: string;
  created_at: string;
  type: 'model' | 'story';
  subject_name?: string;
  status?: string;
};

const ProjectsPage = () => {
  const { axiosInstance } = useAxios();
  const navigate = useNavigate();
  const { showError } = useToast();

  const [allProjects, setAllProjects] = useState<Project[]>([]);

  useEffect(() => {
    const fetchProjects = async () => {
      try {
        const [modelProjects, storyProjects] = await Promise.all([
          getModelProjects(axiosInstance),
          getStoryProjects(axiosInstance),
        ]);

        // Combine and normalize both project types
        const normalizedModelProjects: Project[] = modelProjects.map((p: any) => ({
          id: p.id,
          name: p.name,
          created_at: p.created_at,
          type: 'model' as const,
          subject_name: p.subject_name,
          status: p.status,
        }));

        const normalizedStoryProjects: Project[] = storyProjects.map((p: any) => ({
          id: p._id,
          name: p.name,
          created_at: p.created_at,
          type: 'story' as const,
          status: p.status,
        }));

        // Combine and sort by created_at (newest first)
        const combined = [...normalizedModelProjects, ...normalizedStoryProjects].sort((a, b) => {
          const dateA = new Date(a.created_at).getTime();
          const dateB = new Date(b.created_at).getTime();
          return dateB - dateA; // Newest first
        });

        setAllProjects(combined);
      } catch (error: any) {
        logError('Fetch projects', error);
        showError(getErrorMessage(error, 'Failed to load projects'));
      }
    };
    fetchProjects();
  }, [axiosInstance, showError]);

  const handleCreateProject = (type: 'model' | 'story') => {
    if (type === 'model') {
      navigate('/model-project/new');
    } else {
      navigate('/story-project/new');
    }
  };

  const handleProjectClick = (project: Project) => {
    if (project.type === 'model') {
      navigate(`/model-project/${project.id}`);
    } else {
      navigate(`/story-project/${project.id}`);
    }
  };

  const getProjectTypeLabel = (type: 'model' | 'story') => {
    return type === 'model' ? 'Model Training' : 'Story';
  };

  const getProjectTypeColor = (type: 'model' | 'story') => {
    return type === 'model' ? 'primary' : 'secondary';
  };

  return (
    <DefaultLayout>
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-5xl font-extrabold leading-none">Projects</h1>
        <Dropdown>
          <DropdownTrigger>
            <Button color="primary" endContent={<FontAwesomeIcon icon={faChevronDown} />}>
              <FontAwesomeIcon icon={faPlus} className="mr-2" />
              New Project
            </Button>
          </DropdownTrigger>
          <DropdownMenu aria-label="Project Type Selection" onAction={(key) => handleCreateProject(key as 'model' | 'story')}>
            <DropdownItem
              key="model"
              startContent={<FontAwesomeIcon icon={faWandMagicSparkles} />}
              description="Train an AI model with photos"
            >
              Model Training Project
            </DropdownItem>
            <DropdownItem
              key="story"
              startContent={<FontAwesomeIcon icon={faBook} />}
              description="Create a personalized storybook"
            >
              Story Project
            </DropdownItem>
          </DropdownMenu>
        </Dropdown>
      </div>

      <div className="space-y-3">
        {allProjects.map((project) => (
          <Card
            key={`${project.type}-${project.id}`}
            isPressable
            onPress={() => handleProjectClick(project)}
            className="cursor-pointer"
          >
            <CardBody className="flex flex-row justify-between items-center py-4">
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-1">
                  <h4 className="font-semibold text-lg">{project.name}</h4>
                  <Chip size="sm" color={getProjectTypeColor(project.type)} variant="flat">
                    {getProjectTypeLabel(project.type)}
                  </Chip>
                </div>
                {project.subject_name && (
                  <p className="text-sm text-gray-500">Subject: {project.subject_name}</p>
                )}
              </div>
              <div className="text-right">
                <p className="text-xs text-gray-500">
                  {new Date(project.created_at).toLocaleDateString()}
                </p>
              </div>
            </CardBody>
          </Card>
        ))}
        {allProjects.length === 0 && (
          <div className="text-center py-12">
            <p className="text-gray-500 mb-4">No projects yet. Create one to get started!</p>
            <p className="text-sm text-gray-400">
              Choose between a Model Training project or a Story project above.
            </p>
          </div>
        )}
      </div>
    </DefaultLayout>
  );
};

export default ProjectsPage;
