import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAxios } from '@/hooks/axiosContext';
import { useToast } from '@/hooks/useToast';
import { Spinner } from '@heroui/react';
import DefaultLayout from '@/layouts/default';
import Stepper from '../components/common/stepper';
import ErrorDisplay from '../components/common/errorDisplay';
import KidSetupStep, { KidSetupData } from '../components/steps/storyProjects/kidSetupStep';
import CharacterCreationStep from '../components/steps/storyProjects/characterCreationStep';
import StoryChatStep from '../components/steps/storyProjects/storyChatStep';
import PagesEditorStep from '../components/steps/storyProjects/pagesEditorStep';

// API imports
import { getStoryProjectById, createStoryProject, updateStoryProjectStatus, updateStoryProject } from '../apis/storyProjectController';
import {
  getChildProfileByProject,
  createChildProfile,
  updateChildProfile,
} from '../apis/childProfileController';
import {
  getChatMessages,
  sendChatMessage,
  getStoryState,
  generateStoryState,
  ChatMessage,
  StoryState,
} from '../apis/chatController';
import {
  getStoryPages,
  updatePageText,
  updateIllustrationPrompt,
  generatePageImage,
  compileStory,
  exportStoryPDF,
  StoryPage,
} from '../apis/storyPageController';
import { getErrorMessage, logError } from '@/utils/errorHandling';

const StoryProject: React.FC = () => {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const { axiosInstance } = useAxios();
  const { showError } = useToast();

  // State
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [childProfile, setChildProfile] = useState<any>(null);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [storyState, setStoryState] = useState<StoryState | null>(null);
  const [storyPages, setStoryPages] = useState<StoryPage[]>([]);

  // Loading states
  const [savingProfile, setSavingProfile] = useState(false);
  const [compilingStory, setCompilingStory] = useState(false);

  const steps = [
    { title: 'Kid Setup', description: 'Enter child information and upload photos' },
    { title: 'Character Creation', description: 'Generate and approve character design' },
    { title: 'Story Writing', description: 'Chat with AI to create your story' },
    { title: 'Page Editing', description: 'Edit pages and generate illustrations' },
  ];

  useEffect(() => {
    if (projectId && projectId !== 'new') {
      loadProjectData();
    } else if (projectId === 'new') {
      // New project - start at Kid Setup step
      setLoading(false);
      setCurrentStep(0);
    }
  }, [projectId]);

  const loadProjectData = async () => {
    try {
      setLoading(true);

      // Load project
      const proj = await getStoryProjectById(axiosInstance, projectId!);

      // Determine current step based on project status
      switch (proj.status) {
        case 'DRAFT_SETUP':
          setCurrentStep(0);
          break;
        case 'CHARACTER_PREVIEW':
          setCurrentStep(1);
          break;
        case 'CHAT':
          setCurrentStep(2);
          await loadChatData();
          break;
        case 'ILLUSTRATING':
        case 'READY':
        case 'EXPORTED':
          setCurrentStep(3);
          await loadPagesData();
          break;
        default:
          setCurrentStep(0);
      }

      // Try to load child profile
      const profile = await getChildProfileByProject(axiosInstance, projectId!);
      if (profile) {
        setChildProfile(profile);
        if (proj.status === 'DRAFT_SETUP') {
          setCurrentStep(1); // Move to character creation if profile exists
        }
      }
    } catch (error: any) {
      logError('Load project data', error);

      // If project doesn't exist (404), show not found error
      if (error.response?.status === 404) {
        setError('Project not found. It may have been deleted.');
      } else {
        setError(getErrorMessage(error, 'Failed to load project. Please check your connection and try again.'));
      }
      setLoading(false);
    } finally {
      setLoading(false);
    }
  };

  const loadChatData = async () => {
    try {
      const messages = await getChatMessages(axiosInstance, projectId!);
      setChatMessages(messages);

      const state = await getStoryState(axiosInstance, projectId!);
      setStoryState(state);
    } catch (error: any) {
      logError('Load chat data', error);
      showError(getErrorMessage(error, 'Failed to load chat messages'));
    }
  };

  const loadPagesData = async () => {
    try {
      const pages = await getStoryPages(axiosInstance, projectId!);
      setStoryPages(pages);
    } catch (error: any) {
      logError('Load pages', error);
      showError(getErrorMessage(error, 'Failed to load story pages'));
    }
  };

  // Step 1: Kid Setup
  const handleKidSetupComplete = async (data: KidSetupData) => {
    try {
      setSavingProfile(true);

      let currentProjectId = projectId;

      // If this is a new project, create it first
      if (projectId === 'new') {
        const newProject = await createStoryProject(axiosInstance, data.childName);
        currentProjectId = newProject._id;

        // Update URL to reflect the actual project ID
        navigate(`/story-project/${newProject._id}`, { replace: true });
      }

      if (childProfile) {
        // Update existing profile
        const updatedProfile = await updateChildProfile(axiosInstance, childProfile._id, {
          child_name: data.childName,
          child_age: data.childAge,
        });
        setChildProfile(updatedProfile);

        // Update project name if it changed
        await updateStoryProject(axiosInstance, currentProjectId!, {
          name: data.childName,
        });
      } else {
        // Create new profile
        const newProfile = await createChildProfile(axiosInstance, {
          project_id: currentProjectId!,
          child_name: data.childName,
          child_age: data.childAge,
          consent_given: data.consentGiven,
        });
        setChildProfile(newProfile);
      }

      setCurrentStep(1); // Move to character creation
    } catch (error: any) {
      logError('Save profile', error);
      showError(getErrorMessage(error, 'Failed to save profile. Please try again.'));
    } finally {
      setSavingProfile(false);
    }
  };

  const handleCharacterCreationContinue = async () => {
    try {
      setLoading(true);

      // Update project status to CHAT
      await updateStoryProjectStatus(axiosInstance, projectId!, 'CHAT');

      setCurrentStep(2); // Move to story chat
      await loadChatData();
    } catch (error: any) {
      logError('Move to chat', error);
      showError(getErrorMessage(error, 'Failed to continue. Please try again.'));
    } finally {
      setLoading(false);
    }
  };

  // Step 4: Story Chat
  const handleSendMessage = async (message: string) => {
    try {
      // Optimistically add user message
      const userMsg: ChatMessage = {
        _id: 'temp-' + Date.now(),
        project_id: projectId!,
        user_id: '',
        role: 'user',
        content: message,
        sequence: chatMessages.length + 1,
        created_at: new Date().toISOString(),
      };
      setChatMessages((prev) => [...prev, userMsg]);

      // Send to API
      await sendChatMessage(axiosInstance, projectId!, message);

      // Reload messages to get actual IDs and assistant response
      const updatedMessages = await getChatMessages(axiosInstance, projectId!);
      setChatMessages(updatedMessages);

      // Try to update story state every few messages
      if (updatedMessages.length >= 4 && updatedMessages.length % 3 === 0) {
        try {
          const stateResult = await generateStoryState(axiosInstance, projectId!);
          setStoryState(stateResult.story_state);
        } catch (err) {
          // Ignore errors in story state generation
          console.log('Story state not ready yet');
        }
      }
    } catch (error: any) {
      logError('Send message', error);
      // Remove optimistic message on error
      setChatMessages((prev) => prev.filter((m) => !m._id.startsWith('temp-')));
      showError(getErrorMessage(error, 'Failed to send message. Please try again.'));
      throw error;
    }
  };

  const handleCompileStory = async () => {
    try {
      setCompilingStory(true);

      // Generate final story state if not already done
      if (!storyState || !storyState.title) {
        const stateResult = await generateStoryState(axiosInstance, projectId!);
        setStoryState(stateResult.story_state);
      }

      // Compile story into pages
      const result = await compileStory(axiosInstance, projectId!);
      setStoryPages(result.pages);

      // Move to pages editor
      setCurrentStep(4);
    } catch (error: any) {
      logError('Compile story', error);
      showError(getErrorMessage(error, 'Failed to compile story. Please try again.'));
    } finally {
      setCompilingStory(false);
    }
  };

  // Step 5: Pages Editor
  const handleUpdatePageText = async (pageId: string, text: string) => {
    const updated = await updatePageText(axiosInstance, pageId, text);
    setStoryPages((prev) => prev.map((p) => (p._id === pageId ? updated : p)));
  };

  const handleUpdatePrompt = async (pageId: string, prompt: string) => {
    const updated = await updateIllustrationPrompt(axiosInstance, pageId, prompt);
    setStoryPages((prev) => prev.map((p) => (p._id === pageId ? updated : p)));
  };

  const handleGeneratePageImage = async (pageId: string) => {
    const updated = await generatePageImage(axiosInstance, pageId);
    setStoryPages((prev) => prev.map((p) => (p._id === pageId ? updated : p)));
  };

  const handleExportStory = async () => {
    try {
      setLoading(true);
      await exportStoryPDF(axiosInstance, projectId!);
      // Reload project data to get updated EXPORTED status
      await loadProjectData();
    } catch (error: any) {
      logError('Export story', error);
      showError(getErrorMessage(error, 'Failed to export story. Please try again.'));
    } finally {
      setLoading(false);
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
    const isNotFound = error.includes('not found');
    return (
      <DefaultLayout>
        <div className="container mx-auto px-4">
          <ErrorDisplay
            title={isNotFound ? 'Project Not Found' : 'Error Loading Project'}
            message={error}
            onRetry={() => {
              if (isNotFound) {
                navigate('/projects');
              } else {
                setError(null);
                loadProjectData();
              }
            }}
            retryText={isNotFound ? 'Go to Projects' : 'Retry'}
          />
        </div>
      </DefaultLayout>
    );
  }

  return (
    <DefaultLayout>
      <div className="container mx-auto px-4">
        <Stepper steps={steps} currentStep={currentStep} />

        <div className="mt-8">
          {currentStep === 0 && (
            <KidSetupStep
              onComplete={handleKidSetupComplete}
              loading={savingProfile}
              initialData={childProfile ? {
                childName: childProfile.child_name,
                childAge: childProfile.child_age,
                consentGiven: childProfile.consent_given,
              } : undefined}
            />
          )}

          {currentStep === 1 && (
            <CharacterCreationStep
              projectId={projectId!}
              onContinue={handleCharacterCreationContinue}
              onBack={() => setCurrentStep(0)}
            />
          )}

          {currentStep === 2 && (
            <StoryChatStep
              messages={chatMessages}
              storyState={storyState}
              onSendMessage={handleSendMessage}
              onCompileStory={handleCompileStory}
              onBack={() => setCurrentStep(1)}
              compiling={compilingStory}
            />
          )}

          {currentStep === 3 && (
            <PagesEditorStep
              pages={storyPages}
              onUpdatePageText={handleUpdatePageText}
              onUpdatePrompt={handleUpdatePrompt}
              onGenerateImage={handleGeneratePageImage}
              onBack={() => setCurrentStep(2)}
              onExport={handleExportStory}
            />
          )}
        </div>
      </div>
    </DefaultLayout>
  );
};

export default StoryProject;
