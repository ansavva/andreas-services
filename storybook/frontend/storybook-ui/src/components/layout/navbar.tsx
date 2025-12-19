import { Button } from "@nextui-org/button";
import { Link as NextUILink } from "@nextui-org/link";
import { Link as RouterLink } from "react-router-dom";
import {
  Navbar as NextUINavbar,
  NavbarBrand,
  NavbarContent,
  NavbarItem,
  NavbarMenuToggle,
  NavbarMenu,
  NavbarMenuItem,
} from "@nextui-org/navbar";
import {
  Dropdown,
  DropdownTrigger,
  DropdownMenu,
  DropdownItem
} from "@nextui-org/dropdown";
import { Avatar } from "@nextui-org/avatar";
import { link as linkStyles } from "@nextui-org/theme";
import clsx from "clsx";
import { signInWithRedirect, signOut } from 'aws-amplify/auth';

import { siteConfig } from "@/config/site";
import { ThemeSwitch } from "@/components/common/theme-switch";
import { useUserContext } from "@/hooks/userContext";

export const Navbar = () => {
  const { currentUser, isAuthenticated } = useUserContext();
  const currentPath = window.location.pathname;

  const handleLogin = async () => {
    await signInWithRedirect();
  };

  const handleLogout = async () => {
    await signOut();
  };

  return (
    <NextUINavbar maxWidth="xl" position="sticky">
      <NavbarContent className="basis-1/5 sm:basis-full" justify="start">
        <NavbarBrand className="gap-3 max-w-fit">
          <RouterLink
            className="flex justify-start items-center gap-1"
            to="/"
          >
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
                  "data-[active=true]:font-medium"
                )}
                to={item.href}
              >
                {item.label}
              </RouterLink>
            </NavbarItem>
          ))}
        </div>
      </NavbarContent>

      <NavbarContent
        className="hidden sm:flex basis-1/5 sm:basis-full"
        justify="end"
      >
        <NavbarItem className="hidden sm:flex gap-2">
          <ThemeSwitch />
        </NavbarItem>
        <NavbarItem className="hidden sm:flex">
          {(!isAuthenticated) ? (
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
                  src={currentUser?.picture}
                />
              </DropdownTrigger>
              <DropdownMenu aria-label="Profile Actions" variant="flat">
                <DropdownItem key="profile" className="h-14 gap-2">
                  <p className="font-semibold">Signed in as</p>
                  <p className="font-semibold">{currentUser?.name}</p>
                </DropdownItem>
                <DropdownItem key="logout" color="danger" onClick={handleLogout}>
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
          {(!isAuthenticated) ? (
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
                  src={currentUser?.picture}
                />
              </DropdownTrigger>
              <DropdownMenu aria-label="Profile Actions" variant="flat">
                <DropdownItem key="profile" className="h-14 gap-2">
                  <p className="font-semibold">Signed in as</p>
                  <p className="font-semibold">{currentUser?.name}</p>
                </DropdownItem>
                <DropdownItem key="logout" color="danger" onClick={handleLogout}>
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
                className={clsx(
                  "text-lg",
                  { "text-primary font-medium": currentPath === item.href }
                )}
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
