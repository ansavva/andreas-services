import React, { useState, useEffect, useRef } from "react";
import {
  Button,
  Card,
  CardBody,
  Input,
  Spinner,
  Chip,
  Divider,
} from "@nextui-org/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPaperPlane, faBook } from "@fortawesome/free-solid-svg-icons";

type ChatMessage = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
};

type StoryState = {
  title?: string;
  age_range?: string;
  page_count?: number;
  characters?: any[];
  setting?: string;
  outline?: string[];
  themes?: string[];
};

type StoryChatStepProps = {
  projectId: string;
  messages: ChatMessage[];
  storyState: StoryState | null;
  onSendMessage: (message: string) => Promise<void>;
  onCompileStory: () => Promise<void>;
  onBack: () => void;
  loading: boolean;
  compiling: boolean;
};

const StoryChatStep: React.FC<StoryChatStepProps> = ({
  projectId,
  messages,
  storyState,
  onSendMessage,
  onCompileStory,
  onBack,
  loading,
  compiling,
}) => {
  const [inputMessage, setInputMessage] = useState("");
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages]);

  const handleSend = async () => {
    if (!inputMessage.trim() || sending) return;

    setSending(true);
    try {
      await onSendMessage(inputMessage.trim());
      setInputMessage("");
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const displayedMessages = messages.filter((m) => m.role !== "system");
  const hasEnoughConversation = messages.length >= 4;
  const canCompile = hasEnoughConversation && storyState && storyState.title;

  return (
    <div className="max-w-7xl mx-auto h-[calc(100vh-200px)] flex gap-4">
      {/* Chat Area */}
      <div className="flex-1 flex flex-col">
        <h3 className="text-2xl font-bold mb-2">Create Your Story</h3>
        <p className="text-gray-600 dark:text-gray-400 mb-4">
          Chat with our AI to brainstorm ideas and develop your story
        </p>

        <Card className="flex-1 flex flex-col">
          <CardBody className="flex-1 overflow-y-auto p-4 space-y-4">
            {displayedMessages.length === 0 && (
              <div className="text-center py-12 text-gray-500">
                <p className="mb-2">Start chatting to create your story!</p>
                <p className="text-sm">
                  Try asking: "I want to create a story about going to space"
                </p>
              </div>
            )}

            {displayedMessages.map((message) => (
              <div
                key={message.id}
                className={`flex ${
                  message.role === "user" ? "justify-end" : "justify-start"
                }`}
              >
                <div
                  className={`max-w-[80%] rounded-lg p-3 ${
                    message.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-default-100"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>
              </div>
            ))}

            {sending && (
              <div className="flex justify-start">
                <div className="bg-default-100 rounded-lg p-3">
                  <Spinner size="sm" />
                </div>
              </div>
            )}

            <div ref={messagesEndRef} />
          </CardBody>

          <Divider />

          <div className="p-4">
            <div className="flex gap-2">
              <Input
                value={inputMessage}
                onChange={(e) => setInputMessage(e.target.value)}
                onKeyPress={handleKeyPress}
                placeholder="Type your message..."
                disabled={sending || compiling}
                fullWidth
              />
              <Button
                color="primary"
                isIconOnly
                onPress={handleSend}
                isLoading={sending}
                isDisabled={!inputMessage.trim() || sending || compiling}
              >
                <FontAwesomeIcon icon={faPaperPlane} />
              </Button>
            </div>
          </div>
        </Card>

        <div className="flex justify-between mt-4">
          <Button variant="flat" onPress={onBack} isDisabled={loading || compiling}>
            Back
          </Button>
        </div>
      </div>

      {/* Story Progress Sidebar */}
      <div className="w-80">
        <Card>
          <CardBody className="p-4">
            <h4 className="font-bold mb-4">Story Progress</h4>

            {!storyState && (
              <p className="text-sm text-gray-500">
                Keep chatting to develop your story ideas...
              </p>
            )}

            {storyState && (
              <div className="space-y-4">
                {storyState.title && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Title</p>
                    <p className="font-semibold">{storyState.title}</p>
                  </div>
                )}

                {storyState.age_range && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Age Range</p>
                    <Chip size="sm" color="primary" variant="flat">
                      {storyState.age_range}
                    </Chip>
                  </div>
                )}

                {storyState.page_count && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Pages</p>
                    <p>{storyState.page_count} pages</p>
                  </div>
                )}

                {storyState.setting && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Setting</p>
                    <p className="text-sm">{storyState.setting}</p>
                  </div>
                )}

                {storyState.themes && storyState.themes.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Themes</p>
                    <div className="flex flex-wrap gap-1">
                      {storyState.themes.map((theme, idx) => (
                        <Chip key={idx} size="sm" variant="flat">
                          {theme}
                        </Chip>
                      ))}
                    </div>
                  </div>
                )}

                {storyState.outline && storyState.outline.length > 0 && (
                  <div>
                    <p className="text-xs text-gray-500 mb-1">Outline</p>
                    <ul className="text-sm space-y-1 list-disc list-inside">
                      {storyState.outline.map((point, idx) => (
                        <li key={idx}>{point}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}

            <Divider className="my-4" />

            <Button
              color="success"
              fullWidth
              startContent={<FontAwesomeIcon icon={faBook} />}
              onPress={onCompileStory}
              isLoading={compiling}
              isDisabled={!canCompile || compiling}
            >
              {compiling ? "Compiling Story..." : "Compile Story"}
            </Button>

            {!hasEnoughConversation && (
              <p className="text-xs text-gray-500 mt-2 text-center">
                Chat a bit more to build your story
              </p>
            )}

            {hasEnoughConversation && !storyState?.title && (
              <p className="text-xs text-gray-500 mt-2 text-center">
                Generating story structure...
              </p>
            )}
          </CardBody>
        </Card>
      </div>
    </div>
  );
};

export default StoryChatStep;
