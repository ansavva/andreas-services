import { HeroUIProvider } from "@heroui/react";
import { useNavigate } from "react-router-dom";
import { ThemeProvider as NextThemesProvider } from "next-themes";

export function Provider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();

  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="light"
      enableSystem={false}
      storageKey="storybook-ui-theme"
    >
      <HeroUIProvider navigate={navigate}>{children}</HeroUIProvider>
    </NextThemesProvider>
  );
}
