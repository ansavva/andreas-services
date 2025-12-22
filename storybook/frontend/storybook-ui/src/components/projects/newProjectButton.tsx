import {
  Button,
  Dropdown,
  DropdownTrigger,
  DropdownMenu,
  DropdownItem,
} from "@heroui/react";
import { FontAwesomeIcon } from "@fortawesome/react-fontawesome";
import {
  faPlus,
  faChevronDown,
  faWandMagicSparkles,
  faBook,
} from "@fortawesome/free-solid-svg-icons";

type NewProjectButtonProps = {
  onSelect: (type: "model" | "story") => void;
  buttonProps?: React.ComponentProps<typeof Button>;
};

const NewProjectButton: React.FC<NewProjectButtonProps> = ({
  onSelect,
  buttonProps,
}) => (
  <Dropdown>
    <DropdownTrigger>
      <Button
        color="primary"
        endContent={<FontAwesomeIcon icon={faChevronDown} />}
        {...buttonProps}
      >
        <FontAwesomeIcon className="mr-2" icon={faPlus} />
        New Project
      </Button>
    </DropdownTrigger>
    <DropdownMenu
      aria-label="Project Type Selection"
      onAction={(key) => onSelect(key as "model" | "story")}
    >
      <DropdownItem
        key="model"
        description="Train an AI model with photos"
        startContent={<FontAwesomeIcon icon={faWandMagicSparkles} />}
      >
        Model Training Project
      </DropdownItem>
      <DropdownItem
        key="story"
        description="Create a personalized storybook"
        startContent={<FontAwesomeIcon icon={faBook} />}
      >
        Story Project
      </DropdownItem>
    </DropdownMenu>
  </Dropdown>
);

export default NewProjectButton;
