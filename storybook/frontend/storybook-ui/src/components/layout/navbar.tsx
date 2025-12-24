import {
  Button,
  Navbar as NextUINavbar,
  NavbarBrand,
  NavbarContent,
  NavbarItem,
  NavbarMenuToggle,
  NavbarMenu,
  NavbarMenuItem,
  Dropdown,
  DropdownTrigger,
  DropdownMenu,
  DropdownItem,
  Avatar,
} from "@heroui/react";
import { Link as RouterLink, useNavigate } from "react-router-dom";
import { link as linkStyles } from "@heroui/theme";
import clsx from "clsx";
import { signInWithRedirect, signOut } from "aws-amplify/auth";
import { useState, useEffect } from "react";

import { siteConfig } from "@/config/site";
import { ThemeSwitch } from "@/components/common/theme-switch";
import { useUserContext } from "@/hooks/userContext";
import { useAxios } from "@/hooks/axiosContext";
import { getMyProfile } from "@/apis/userProfileController";
import { downloadImageById } from "@/apis/imageController";
import NewProjectButton from "@/components/projects/newProjectButton";

export const Navbar = () => {
  const { currentUser, isAuthenticated } = useUserContext();
  const { axiosInstance } = useAxios();
  const currentPath = window.location.pathname;
  const navigate = useNavigate();
  const [profileImageUrl, setProfileImageUrl] = useState<string | null>(null);
  const [displayName, setDisplayName] = useState<string | null>(null);

  // Fetch user profile on mount
  useEffect(() => {
    if (isAuthenticated && axiosInstance) {
      fetchUserProfile();
    }
  }, [isAuthenticated, axiosInstance]);

  const fetchUserProfile = async () => {
    try {
      const profile = await getMyProfile(axiosInstance);

      setDisplayName(profile.display_name);

      // Fetch profile image if exists
      if (profile.profile_image_id) {
        const response = await downloadImageById(
          axiosInstance,
          profile.profile_image_id,
        );
        const reader = new FileReader();

        reader.onloadend = () => {
          setProfileImageUrl(reader.result as string);
        };
        reader.readAsDataURL(response);
      }
    } catch (error) {
      console.error("Error fetching profile:", error);
    }
  };

  const handleLogin = async () => {
    await signInWithRedirect();
  };

  const handleLogout = async () => {
    await signOut();
  };

  const handleCreateProject = (type: "model" | "story") => {
    if (type === "model") {
      navigate("/model-project/new");
    } else {
      navigate("/story-project/new");
    }
  };

  return (
    <NextUINavbar maxWidth="xl" position="sticky">
      <NavbarContent className="basis-1/5 sm:basis-full" justify="start">
        <NavbarBrand className="gap-3 max-w-fit">
          <RouterLink className="flex justify-start items-center gap-1" to="/">
            <p className="font-bold text-inherit">Storybook</p>
          </RouterLink>
        </NavbarBrand>
        <div className="hidden sm:flex gap-4 justify-start ml-2">
          {siteConfig.navItems.map((item) => (
            <NavbarItem key={item.href}>
              <RouterLink
                className={clsx(
                  linkStyles({ color: "foreground" }),
                  {
                    "text-primary font-medium": currentPath === item.href,
                  },
                  "data-[active=true]:font-medium",
                )}
                to={item.href}
              >
                {item.label}
              </RouterLink>
            </NavbarItem>
          ))}
        </div>
        <NavbarItem className="hidden sm:flex">
          <NewProjectButton
            buttonProps={{ size: "sm", variant: "flat", color: "primary" }}
            onSelect={handleCreateProject}
          />
        </NavbarItem>
      </NavbarContent>

      <NavbarContent
        className="hidden sm:flex basis-1/5 sm:basis-full"
        justify="end"
      >
        <NavbarItem className="hidden sm:flex gap-2">
          <ThemeSwitch />
        </NavbarItem>
        <NavbarItem className="hidden sm:flex">
          {!isAuthenticated ? (
            <Button
              className="text-sm font-normal text-default-600 bg-default-100"
              variant="flat"
              onClick={handleLogin}
            >
              Login
            </Button>
          ) : (
            <Dropdown placement="bottom-end">
              <DropdownTrigger>
                <Avatar
                  isBordered
                  as="button"
                  className="transition-transform"
                  name={displayName || currentUser?.username}
                  src={profileImageUrl || undefined}
                />
              </DropdownTrigger>
              <DropdownMenu aria-label="Profile Actions" variant="flat">
                <DropdownItem key="profile-info" className="h-14 gap-2">
                  <p className="font-semibold">Signed in as</p>
                  <p className="font-semibold">
                    {displayName || currentUser?.name || currentUser?.username}
                  </p>
                </DropdownItem>
                <DropdownItem key="profile" as={RouterLink} to="/profile">
                  Profile Settings
                </DropdownItem>
                <DropdownItem
                  key="logout"
                  color="danger"
                  onClick={handleLogout}
                >
                  Log Out
                </DropdownItem>
              </DropdownMenu>
            </Dropdown>
          )}
        </NavbarItem>
      </NavbarContent>

      <NavbarContent className="sm:hidden basis-1 pl-4" justify="end">
        <ThemeSwitch />
        <NavbarItem>
          {!isAuthenticated ? (
            <Button
              className="text-sm font-normal text-default-600 bg-default-100"
              variant="flat"
              onClick={handleLogin}
            >
              Login
            </Button>
          ) : (
            <Dropdown placement="bottom-end">
              <DropdownTrigger>
                <Avatar
                  isBordered
                  as="button"
                  className="transition-transform"
                  name={displayName || currentUser?.username}
                  src={profileImageUrl || undefined}
                />
              </DropdownTrigger>
              <DropdownMenu aria-label="Profile Actions" variant="flat">
                <DropdownItem key="profile-info" className="h-14 gap-2">
                  <p className="font-semibold">Signed in as</p>
                  <p className="font-semibold">
                    {displayName || currentUser?.name || currentUser?.username}
                  </p>
                </DropdownItem>
                <DropdownItem key="profile" as={RouterLink} to="/profile">
                  Profile Settings
                </DropdownItem>
                <DropdownItem
                  key="logout"
                  color="danger"
                  onClick={handleLogout}
                >
                  Log Out
                </DropdownItem>
              </DropdownMenu>
            </Dropdown>
          )}
        </NavbarItem>
        <NavbarMenuToggle />
      </NavbarContent>

      <NavbarMenu>
        <div className="mx-4 mt-2 flex flex-col gap-2">
          {siteConfig.navMenuItems.map((item, index) => (
            <NavbarMenuItem key={`${item}-${index}`}>
              <RouterLink
                className={clsx("text-lg", {
                  "text-primary font-medium": currentPath === item.href,
                })}
                to={item.href}
              >
                {item.label}
              </RouterLink>
            </NavbarMenuItem>
          ))}
        </div>
      </NavbarMenu>
    </NextUINavbar>
  );
};
