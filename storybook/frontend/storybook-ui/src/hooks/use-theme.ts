import { useMemo } from "react";
import { useTheme as useNextTheme } from "next-themes";

type ThemeMode = "light" | "dark";

export const useTheme = () => {
  const { theme, setTheme, resolvedTheme } = useNextTheme();

  const currentTheme = useMemo<ThemeMode>(() => {
    const value = theme === "system" ? resolvedTheme : theme;

    return (value as ThemeMode) || "light";
  }, [theme, resolvedTheme]);

  const isDark = currentTheme === "dark";
  const isLight = currentTheme === "light";

  const setLightTheme = () => setTheme("light");
  const setDarkTheme = () => setTheme("dark");
  const toggleTheme = () => setTheme(isDark ? "light" : "dark");

  return {
    theme: currentTheme,
    isDark,
    isLight,
    setLightTheme,
    setDarkTheme,
    toggleTheme,
  };
};
