import React, { useState } from 'react';
import { Card, CardBody, CardHeader, Button, Textarea, Spinner, Chip } from '@nextui-org/react';
import { FontAwesomeIcon } from '@fortawesome/react-fontawesome';
import { faArrowLeft, faImage, faEdit, faSave, faTimes, faRedo } from '@fortawesome/free-solid-svg-icons';
import { StoryPage } from '../apis/storyPageController';

interface PagesEditorStepProps {
  projectId: string;
  pages: StoryPage[];
  onUpdatePageText: (pageId: string, text: string) => Promise<void>;
  onUpdatePrompt: (pageId: string, prompt: string) => Promise<void>;
  onGenerateImage: (pageId: string) => Promise<void>;
  onBack: () => void;
  onExport: () => void;
  loading?: boolean;
}

const PagesEditorStep: React.FC<PagesEditorStepProps> = ({
  projectId,
  pages,
  onUpdatePageText,
  onUpdatePrompt,
  onGenerateImage,
  onBack,
  onExport,
  loading = false,
}) => {
  const [selectedPage, setSelectedPage] = useState<number>(0);
  const [editingText, setEditingText] = useState(false);
  const [editingPrompt, setEditingPrompt] = useState(false);
  const [textDraft, setTextDraft] = useState('');
  const [promptDraft, setPromptDraft] = useState('');
  const [generatingImage, setGeneratingImage] = useState<string | null>(null);
  const [savingText, setSavingText] = useState(false);
  const [savingPrompt, setSavingPrompt] = useState(false);

  const currentPage = pages[selectedPage];

  const handleStartEditText = () => {
    setTextDraft(currentPage.page_text);
    setEditingText(true);
  };

  const handleSaveText = async () => {
    try {
      setSavingText(true);
      await onUpdatePageText(currentPage._id, textDraft);
      setEditingText(false);
    } catch (error) {
      console.error('Error saving text:', error);
      alert('Failed to save text. Please try again.');
    } finally {
      setSavingText(false);
    }
  };

  const handleCancelEditText = () => {
    setEditingText(false);
    setTextDraft('');
  };

  const handleStartEditPrompt = () => {
    setPromptDraft(currentPage.illustration_prompt || '');
    setEditingPrompt(true);
  };

  const handleSavePrompt = async () => {
    try {
      setSavingPrompt(true);
      await onUpdatePrompt(currentPage._id, promptDraft);
      setEditingPrompt(false);
    } catch (error) {
      console.error('Error saving prompt:', error);
      alert('Failed to save prompt. Please try again.');
    } finally {
      setSavingPrompt(false);
    }
  };

  const handleCancelEditPrompt = () => {
    setEditingPrompt(false);
    setPromptDraft('');
  };

  const handleGenerateImage = async () => {
    try {
      setGeneratingImage(currentPage._id);
      await onGenerateImage(currentPage._id);
    } catch (error) {
      console.error('Error generating image:', error);
      alert('Failed to generate image. Please try again.');
    } finally {
      setGeneratingImage(null);
    }
  };

  if (!currentPage) {
    return (
      <Card>
        <CardBody>
          <p className="text-center text-gray-500">No pages available</p>
        </CardBody>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex justify-between items-center">
        <Button
          variant="light"
          startContent={<FontAwesomeIcon icon={faArrowLeft} />}
          onPress={onBack}
        >
          Back
        </Button>
        <h2 className="text-2xl font-bold">Pages Editor</h2>
        <Button color="success" onPress={onExport}>
          Export Story
        </Button>
      </div>

      {/* Page Navigation */}
      <div className="flex gap-2 overflow-x-auto pb-2">
        {pages.map((page, index) => (
          <Button
            key={page._id}
            size="sm"
            color={selectedPage === index ? 'primary' : 'default'}
            variant={selectedPage === index ? 'solid' : 'bordered'}
            onPress={() => setSelectedPage(index)}
            className="min-w-[80px]"
          >
            Page {page.page_number}
            {page.image_s3_key && (
              <Chip size="sm" color="success" className="ml-1">
                <FontAwesomeIcon icon={faImage} className="text-xs" />
              </Chip>
            )}
          </Button>
        ))}
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Text Editor */}
        <Card>
          <CardHeader className="flex justify-between items-center">
            <h3 className="text-lg font-semibold">Page Text</h3>
            {!editingText && (
              <Button
                size="sm"
                variant="light"
                startContent={<FontAwesomeIcon icon={faEdit} />}
                onPress={handleStartEditText}
              >
                Edit
              </Button>
            )}
          </CardHeader>
          <CardBody>
            {editingText ? (
              <div className="space-y-4">
                <Textarea
                  value={textDraft}
                  onValueChange={setTextDraft}
                  minRows={4}
                  placeholder="Enter page text..."
                />
                <div className="flex gap-2">
                  <Button
                    color="primary"
                    startContent={<FontAwesomeIcon icon={faSave} />}
                    onPress={handleSaveText}
                    isLoading={savingText}
                  >
                    Save
                  </Button>
                  <Button
                    variant="light"
                    startContent={<FontAwesomeIcon icon={faTimes} />}
                    onPress={handleCancelEditText}
                    isDisabled={savingText}
                  >
                    Cancel
                  </Button>
                </div>
                <p className="text-xs text-gray-500">
                  Version: {currentPage.text_version} (saving will create version {currentPage.text_version + 1})
                </p>
              </div>
            ) : (
              <div>
                <p className="whitespace-pre-wrap">{currentPage.page_text}</p>
                <p className="text-xs text-gray-500 mt-2">Version: {currentPage.text_version}</p>
              </div>
            )}
          </CardBody>
        </Card>

        {/* Illustration Preview */}
        <Card>
          <CardHeader>
            <h3 className="text-lg font-semibold">Illustration</h3>
          </CardHeader>
          <CardBody>
            {currentPage.image_s3_key ? (
              <div className="space-y-4">
                <div className="aspect-square bg-gray-100 rounded-lg flex items-center justify-center">
                  {/* TODO: Display actual image from S3 */}
                  <p className="text-gray-500">Image: {currentPage.image_s3_key}</p>
                </div>
                <div className="flex gap-2">
                  <Button
                    color="primary"
                    variant="bordered"
                    startContent={<FontAwesomeIcon icon={faRedo} />}
                    onPress={handleGenerateImage}
                    isLoading={generatingImage === currentPage._id}
                  >
                    Regenerate
                  </Button>
                </div>
                <p className="text-xs text-gray-500">Version: {currentPage.image_version}</p>
              </div>
            ) : (
              <div className="space-y-4">
                <div className="aspect-square bg-gray-100 rounded-lg flex items-center justify-center">
                  <div className="text-center text-gray-500">
                    <FontAwesomeIcon icon={faImage} className="text-4xl mb-2" />
                    <p>No image generated yet</p>
                  </div>
                </div>
                <Button
                  color="primary"
                  startContent={<FontAwesomeIcon icon={faImage} />}
                  onPress={handleGenerateImage}
                  isLoading={generatingImage === currentPage._id}
                  isDisabled={!currentPage.illustration_prompt}
                >
                  Generate Image
                </Button>
              </div>
            )}
          </CardBody>
        </Card>
      </div>

      {/* Illustration Prompt Editor */}
      <Card>
        <CardHeader className="flex justify-between items-center">
          <h3 className="text-lg font-semibold">Illustration Prompt</h3>
          {!editingPrompt && (
            <Button
              size="sm"
              variant="light"
              startContent={<FontAwesomeIcon icon={faEdit} />}
              onPress={handleStartEditPrompt}
            >
              Edit
            </Button>
          )}
        </CardHeader>
        <CardBody>
          {editingPrompt ? (
            <div className="space-y-4">
              <Textarea
                value={promptDraft}
                onValueChange={setPromptDraft}
                minRows={3}
                placeholder="Describe what should be illustrated on this page..."
                description="This prompt will be used to generate the illustration using AI"
              />
              <div className="flex gap-2">
                <Button
                  color="primary"
                  startContent={<FontAwesomeIcon icon={faSave} />}
                  onPress={handleSavePrompt}
                  isLoading={savingPrompt}
                >
                  Save
                </Button>
                <Button
                  variant="light"
                  startContent={<FontAwesomeIcon icon={faTimes} />}
                  onPress={handleCancelEditPrompt}
                  isDisabled={savingPrompt}
                >
                  Cancel
                </Button>
              </div>
            </div>
          ) : (
            <div>
              <p className="whitespace-pre-wrap">{currentPage.illustration_prompt || 'No prompt set'}</p>
            </div>
          )}
        </CardBody>
      </Card>

      {/* Progress Info */}
      <Card>
        <CardBody>
          <div className="flex justify-between items-center">
            <div>
              <p className="font-semibold">Story Progress</p>
              <p className="text-sm text-gray-500">
                {pages.filter(p => p.image_s3_key).length} of {pages.length} pages illustrated
              </p>
            </div>
            {pages.every(p => p.image_s3_key) && (
              <Chip color="success" variant="flat">
                All pages complete!
              </Chip>
            )}
          </div>
        </CardBody>
      </Card>
    </div>
  );
};

export default PagesEditorStep;
