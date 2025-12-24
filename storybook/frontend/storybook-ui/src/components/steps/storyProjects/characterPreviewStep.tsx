import React, { useState } from "react";
import { Button, Card, CardBody, Spinner, Tabs, Tab } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faRefresh, faCheck } from "@fortawesome/free-solid-svg-icons";

import ImageGrid from "@/components/images/imageGrid";

type CharacterAsset = {
  id: string;
  asset_type: string;
  image_id: string;
  scene_name?: string;
  is_approved: boolean;
  version: number;
};

type CharacterPreviewStepProps = {
  projectId: string;
  portrait: CharacterAsset | null;
  previewScenes: CharacterAsset[];
  onGeneratePortrait: () => Promise<void>;
  onGenerateScenes: () => Promise<void>;
  onRegenerateAsset: (assetId: string) => Promise<void>;
  onApproveAsset: (assetId: string) => Promise<void>;
  onContinue: () => void;
  onBack: () => void;
  loading: boolean;
  generatingPortrait: boolean;
  generatingScenes: boolean;
};

const CharacterPreviewStep: React.FC<CharacterPreviewStepProps> = ({
  projectId,
  portrait,
  previewScenes,
  onGeneratePortrait,
  onGenerateScenes,
  onRegenerateAsset,
  onApproveAsset,
  onContinue,
  onBack,
  loading,
  generatingPortrait,
  generatingScenes,
}) => {
  const [activeTab, setActiveTab] = useState("portrait");

  const hasApprovedPortrait = portrait?.is_approved;
  const hasScenes = previewScenes.length > 0;
  const canContinue = hasApprovedPortrait;

  // Convert portrait to ImageGrid format
  const portraitImages = portrait
    ? [
        {
          id: portrait.image_id,
          name: "Character Portrait",
        },
      ]
    : [];

  // Convert scenes to ImageGrid format
  const sceneImages = previewScenes.map((scene) => ({
    id: scene.image_id,
    name: scene.scene_name || "Preview Scene",
  }));

  // Custom actions for portrait modal
  const renderPortraitActions = (image: any) => {
    if (!portrait) return null;

    return (
      <>
        <Button
          color={portrait.is_approved ? "success" : "default"}
          isDisabled={portrait.is_approved}
          startContent={<FontAwesomeIcon icon={faCheck} />}
          variant={portrait.is_approved ? "solid" : "flat"}
          onPress={() => onApproveAsset(portrait.id)}
        >
          {portrait.is_approved ? "Approved" : "Approve"}
        </Button>
        <Button
          startContent={<FontAwesomeIcon icon={faRefresh} />}
          variant="flat"
          onPress={() => onRegenerateAsset(portrait.id)}
        >
          Regenerate
        </Button>
      </>
    );
  };

  // Custom actions for scene modals
  const renderSceneActions = (image: any) => {
    const scene = previewScenes.find((s) => s.id === image.id);

    if (!scene) return null;

    return (
      <Button
        startContent={<FontAwesomeIcon icon={faRefresh} />}
        variant="flat"
        onPress={() => onRegenerateAsset(scene.id)}
      >
        Regenerate
      </Button>
    );
  };

  return (
    <div className="max-w-6xl mx-auto">
      <h3 className="text-2xl font-bold mb-2">Character Preview</h3>
      <p className="text-gray-600 dark:text-gray-400 mb-6">
        Review your child's character portrait and see them in different scenes.
        Approve the portrait you like best to continue.
      </p>

      <Tabs
        className="mb-6"
        selectedKey={activeTab}
        onSelectionChange={(key) => setActiveTab(key as string)}
      >
        <Tab key="portrait" title="Portrait">
          <Card>
            <CardBody className="text-center p-8">
              {!portrait && !generatingPortrait && (
                <div>
                  <p className="mb-4 text-gray-600 dark:text-gray-400">
                    Generate a character portrait to get started
                  </p>
                  <Button
                    color="primary"
                    isLoading={generatingPortrait}
                    size="lg"
                    onPress={onGeneratePortrait}
                  >
                    Generate Portrait
                  </Button>
                </div>
              )}

              {generatingPortrait && (
                <div className="py-12">
                  <Spinner size="lg" />
                  <p className="mt-4 text-gray-600 dark:text-gray-400">
                    Generating character portrait...
                  </p>
                </div>
              )}

              {portrait && !generatingPortrait && (
                <div className="max-w-md mx-auto">
                  <ImageGrid
                    customActions={renderPortraitActions}
                    images={portraitImages}
                  />

                  {!hasScenes && portrait.is_approved && (
                    <div className="mt-6 p-4 bg-primary-50 dark:bg-primary-900/20 rounded-lg">
                      <p className="mb-3">
                        Great! Now let's see your character in fun preview
                        scenes.
                      </p>
                      <Button
                        color="primary"
                        isLoading={generatingScenes}
                        onPress={onGenerateScenes}
                      >
                        Generate Preview Scenes
                      </Button>
                    </div>
                  )}
                </div>
              )}
            </CardBody>
          </Card>
        </Tab>

        <Tab
          key="scenes"
          isDisabled={!hasApprovedPortrait}
          title="Preview Scenes"
        >
          <Card>
            <CardBody className="p-8">
              {!hasScenes && !generatingScenes && hasApprovedPortrait && (
                <div className="text-center">
                  <p className="mb-4 text-gray-600 dark:text-gray-400">
                    Generate preview scenes to see your character in action!
                  </p>
                  <Button
                    color="primary"
                    isLoading={generatingScenes}
                    size="lg"
                    onPress={onGenerateScenes}
                  >
                    Generate Preview Scenes
                  </Button>
                </div>
              )}

              {generatingScenes && (
                <div className="text-center py-12">
                  <Spinner size="lg" />
                  <p className="mt-4 text-gray-600 dark:text-gray-400">
                    Generating preview scenes...
                  </p>
                </div>
              )}

              {hasScenes && !generatingScenes && (
                <ImageGrid
                  customActions={renderSceneActions}
                  images={sceneImages}
                />
              )}
            </CardBody>
          </Card>
        </Tab>
      </Tabs>

      <div className="flex justify-between mt-6">
        <Button isDisabled={loading} variant="flat" onPress={onBack}>
          Back
        </Button>
        <Button
          color="primary"
          isDisabled={!canContinue || loading}
          isLoading={loading}
          size="lg"
          onPress={onContinue}
        >
          Continue to Story Chat
        </Button>
      </div>
    </div>
  );
};

export default CharacterPreviewStep;
