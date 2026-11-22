import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";

type Theme = "light" | "dark" | "system";

export function ThemeSelector() {
  const [theme, setTheme] = useState<Theme>("system");

  useEffect(() => {
    const preference = window.matchMedia("(prefers-color-scheme: dark)");
    const stored = window.localStorage.getItem("auction-theme");
    const selected = stored === "light" || stored === "dark" ? stored : "system";
    setTheme(selected);
    function apply() {
      const saved = window.localStorage.getItem("auction-theme");
      document.documentElement.classList.toggle("dark",
        saved === "dark" || (saved !== "light" && preference.matches));
    }
    apply();
    preference.addEventListener("change", apply);
    return () => preference.removeEventListener("change", apply);
  }, []);

  function update(value: Theme) {
    window.localStorage.setItem("auction-theme", value);
    setTheme(value);
    document.documentElement.classList.toggle("dark",
      value === "dark" || (value === "system" && window.matchMedia("(prefers-color-scheme: dark)").matches));
  }

  return (
    <label className="flex items-center gap-2 text-sm">
      {theme === "dark" ? <Moon size={17} aria-hidden /> : <Sun size={17} aria-hidden />}
      <span className="sr-only">Theme</span>
      <select className="field w-auto" value={theme} onChange={(event) => update(event.target.value as Theme)}>
        <option value="system">System</option>
        <option value="light">Light</option>
        <option value="dark">Dark</option>
      </select>
    </label>
  );
}
