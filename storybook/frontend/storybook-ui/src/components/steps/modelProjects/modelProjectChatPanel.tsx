import React, { useEffect, useRef, useState } from "react";
import { Button, Card, CardBody, Divider, Input, Spinner } from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import { faPaperPlane } from "@fortawesome/free-solid-svg-icons";

import { useAxios } from "@/hooks/axiosContext";
import { useToast } from "@/hooks/useToast";
import {
  ChatMessage,
  getModelProjectChatMessages,
  sendModelProjectChatMessage,
} from "@/apis/chatController";
import { getErrorMessage } from "@/utils/errorHandling";

type ModelProjectChatPanelProps = {
  projectId: string;
};

const ModelProjectChatPanel: React.FC<ModelProjectChatPanelProps> = ({ projectId }) => {
  const { axiosInstance } = useAxios();
  const { showError } = useToast();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [inputMessage, setInputMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const fetchMessages = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const items = await getModelProjectChatMessages(axiosInstance, projectId);
      setMessages(items.filter((msg) => msg.role !== "system"));
    } catch (error) {
      showError(getErrorMessage(error, "Failed to load chat messages."));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchMessages();
  }, [projectId]);

  useEffect(() => {
    scrollToBottom();
  }, [messages, sending]);

  const handleSend = async () => {
    if (!inputMessage.trim() || sending) return;
    const nextMessage = inputMessage.trim();
    const optimisticMessage: ChatMessage = {
      _id: `temp-${Date.now()}`,
      project_id: projectId,
      user_id: "",
      role: "user",
      content: nextMessage,
      sequence: messages.length + 1,
      created_at: new Date().toISOString(),
    };
    setMessages((prev) => [...prev, optimisticMessage]);
    setInputMessage("");
    setSending(true);
    try {
      await sendModelProjectChatMessage(axiosInstance, projectId, nextMessage);
      await fetchMessages();
    } catch (error) {
      setMessages((prev) => prev.filter((msg) => msg._id !== optimisticMessage._id));
      showError(getErrorMessage(error, "Failed to send message."));
    } finally {
      setSending(false);
    }
  };

  const handleKeyPress = (event: React.KeyboardEvent) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      handleSend();
    }
  };

  return (
    <Card className="h-full min-h-[360px]">
      <CardBody className="flex flex-col h-full p-4 min-h-0">
        <div className="mb-3">
          <h3 className="text-lg font-semibold">Project Chat</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Brainstorm prompt ideas with AI.
          </p>
        </div>

        <div className="flex-1 min-h-0 overflow-y-auto space-y-3 pr-1">
          {loading ? (
            <div className="flex justify-center py-6">
              <Spinner size="sm" />
            </div>
          ) : messages.length === 0 ? (
            <div className="text-sm text-gray-500 dark:text-gray-400">
              Start a conversation to generate prompt ideas.
            </div>
          ) : (
            messages.map((message) => (
              <div
                key={message._id}
                className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[80%] rounded-lg px-3 py-2 text-sm ${
                    message.role === "user"
                      ? "bg-primary text-primary-foreground"
                      : "bg-default-100"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{message.content}</p>
                </div>
              </div>
            ))
          )}
          {sending && (
            <div className="flex justify-start">
              <div className="bg-default-100 rounded-lg px-3 py-2 text-sm">
                <Spinner size="sm" />
              </div>
            </div>
          )}
          <div ref={messagesEndRef} />
        </div>

        <Divider className="my-3" />

        <div className="flex gap-2">
          <Input
            fullWidth
            disabled={sending}
            placeholder="Ask for prompt ideas..."
            value={inputMessage}
            onChange={(event) => setInputMessage(event.target.value)}
            onKeyPress={handleKeyPress}
          />
          <Button
            isIconOnly
            color="primary"
            isDisabled={!inputMessage.trim() || sending}
            isLoading={sending}
            onPress={handleSend}
          >
            <FontAwesomeIcon icon={faPaperPlane} />
          </Button>
        </div>
      </CardBody>
    </Card>
  );
};

export default ModelProjectChatPanel;
