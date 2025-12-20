import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useAxios } from '@/hooks/axiosContext';
import { useToast } from '@/hooks/useToast';
import { Card, CardBody, Spinner } from '@heroui/react';
import DefaultLayout from '@/layouts/default';
import Stepper from '../components/common/stepper';
import ErrorDisplay from '../components/common/errorDisplay';
import KidSetupStep, { KidSetupData } from '../components/steps/kidSetupStep';
import CharacterCreationStep from '../components/steps/characterCreationStep';
import StoryChatStep from '../components/steps/storyChatStep';
import PagesEditorStep from '../components/steps/pagesEditorStep';

// API imports
import { getStoryProjectById, createStoryProject, updateStoryProjectStatus, updateStoryProject } from '../apis/storyProjectController';
import {
  getChildProfileByProject,
  createChildProfile,
  updateChildProfile,
} from '../apis/childProfileController';
import {
  getCharacterAssets,
  generateCharacterPortrait,
  generatePreviewScenes,
  approveCharacterAsset,
  regenerateCharacterAsset,
  CharacterAsset,
} from '../apis/characterController';
import {
  getChatMessages,
  sendChatMessage,
  getStoryState,
  generateStoryState,
  ChatMessage,
  StoryState,
} from '../apis/chatController';
import { uploadImage } from '../apis/imageController';
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
  const { showError, showSuccess } = useToast();

  // State
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [currentStep, setCurrentStep] = useState(0);
  const [project, setProject] = useState<any>(null);
  const [childProfile, setChildProfile] = useState<any>(null);
  const [portrait, setPortrait] = useState<CharacterAsset | null>(null);
  const [previewScenes, setPreviewScenes] = useState<CharacterAsset[]>([]);
  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([]);
  const [storyState, setStoryState] = useState<StoryState | null>(null);
  const [storyPages, setStoryPages] = useState<StoryPage[]>([]);

  // Loading states
  const [savingProfile, setSavingProfile] = useState(false);
  const [uploadingPhotos, setUploadingPhotos] = useState(false);
  const [generatingPortrait, setGeneratingPortrait] = useState(false);
  const [generatingScenes, setGeneratingScenes] = useState(false);
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
      setProject(proj);

      // Determine current step based on project status
      switch (proj.status) {
        case 'DRAFT_SETUP':
          setCurrentStep(0);
          break;
        case 'CHARACTER_PREVIEW':
          setCurrentStep(1);
          await loadCharacterAssets();
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

  const loadCharacterAssets = async () => {
    try {
      const assets = await getCharacterAssets(axiosInstance, projectId!);
      const portraitAsset = assets.find((a) => a.asset_type === 'portrait');
      const sceneAssets = assets.filter((a) => a.asset_type === 'preview_scene');

      setPortrait(portraitAsset || null);
      setPreviewScenes(sceneAssets);
    } catch (error: any) {
      logError('Load character assets', error);
      showError(getErrorMessage(error, 'Failed to load character assets'));
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
        setProject(newProject);
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

        // Reload project to get updated name
        const updatedProject = await getStoryProjectById(axiosInstance, currentProjectId!);
        setProject(updatedProject);
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

  // Step 2: Photo Upload
  const handlePhotoUploadComplete = async (photoIds: string[]) => {
    try {
      setUploadingPhotos(true);

      // Photos are already uploaded, just update child profile with photo IDs
      await updateChildProfile(axiosInstance, childProfile._id, {
        photo_ids: photoIds,
      });

      // Update project status
      await updateStoryProjectStatus(axiosInstance, projectId!, 'CHARACTER_PREVIEW');

      // Reload child profile
      const updatedProfile = await getChildProfileByProject(axiosInstance, projectId!);
      setChildProfile(updatedProfile);

      setCurrentStep(2); // Move to character preview
    } catch (error: any) {
      logError('Update profile with photos', error);
      showError(getErrorMessage(error, 'Failed to update profile. Please try again.'));
    } finally {
      setUploadingPhotos(false);
    }
  };

  // Step 3: Character Preview
  const handleGeneratePortrait = async () => {
    try {
      setGeneratingPortrait(true);
      const newPortrait = await generateCharacterPortrait(axiosInstance, projectId!);
      setPortrait(newPortrait);
    } catch (error: any) {
      logError('Generate portrait', error);
      showError(getErrorMessage(error, 'Failed to generate portrait. Please try again.'));
    } finally {
      setGeneratingPortrait(false);
    }
  };

  const handleGenerateScenes = async () => {
    try {
      setGeneratingScenes(true);
      const result = await generatePreviewScenes(axiosInstance, projectId!);
      setPreviewScenes(result.scenes);
    } catch (error: any) {
      logError('Generate scenes', error);
      showError(getErrorMessage(error, 'Failed to generate scenes. Please try again.'));
    } finally {
      setGeneratingScenes(false);
    }
  };

  const handleApproveAsset = async (assetId: string) => {
    try {
      const approved = await approveCharacterAsset(axiosInstance, assetId);

      // Update local state
      if (portrait && portrait._id === assetId) {
        setPortrait(approved);
      }
    } catch (error: any) {
      logError('Approve asset', error);
      showError(getErrorMessage(error, 'Failed to approve asset. Please try again.'));
    }
  };

  const handleRegenerateAsset = async (assetId: string) => {
    try {
      const newAsset = await regenerateCharacterAsset(axiosInstance, assetId);

      // Update local state
      if (portrait && portrait._id === assetId) {
        setPortrait(newAsset);
      } else {
        // Update scene
        setPreviewScenes((prev) => prev.map((s) => (s._id === assetId ? newAsset : s)));
      }
    } catch (error: any) {
      logError('Regenerate asset', error);
      showError(getErrorMessage(error, 'Failed to regenerate asset. Please try again.'));
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
      const response = await sendChatMessage(axiosInstance, projectId!, message);

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
        <div className="container mx-auto px-4 py-8">
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
      <div className="container mx-auto px-4 py-8">
        <Stepper steps={steps} currentStep={currentStep} />

        <div className="mt-8">
          {currentStep === 0 && (
            <KidSetupStep
              projectId={projectId!}
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
              projectId={projectId!}
              messages={chatMessages}
              storyState={storyState}
              onSendMessage={handleSendMessage}
              onCompileStory={handleCompileStory}
              onBack={() => setCurrentStep(1)}
              loading={loading}
              compiling={compilingStory}
            />
          )}

          {currentStep === 3 && (
            <PagesEditorStep
              projectId={projectId!}
              pages={storyPages}
              onUpdatePageText={handleUpdatePageText}
              onUpdatePrompt={handleUpdatePrompt}
              onGenerateImage={handleGeneratePageImage}
              onBack={() => setCurrentStep(2)}
              onExport={handleExportStory}
              loading={loading}
            />
          )}
        </div>
      </div>
    </DefaultLayout>
  );
};

export default StoryProject;
