import { useRouter } from "vue-router";

function navigateWithFlag(path: string, flag: string) {
  const router = useRouter();

  return () => router.push({ path, query: { [flag]: "1" } });
}

export function useGlobalQuickActions() {
  return {
    openEnvironmentChecks: navigateWithFlag("/environment", "autorun"),
    openScriptUpload: navigateWithFlag("/scripts", "upload"),
  };
}
