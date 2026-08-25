import { useRouter } from "vue-router";

function navigateWithFlag(path: string, flag: string) {
  const router = useRouter();

  return () => router.push({ path, query: { [flag]: "1" } });
}

export function useGlobalQuickActions() {
  return {
    openEnvironmentChecks: navigateWithFlag("/environment", "autorun"),
    runAllHealthChecks: navigateWithFlag("/checks", "runAll"),
    openTaskCreate: navigateWithFlag("/tasks", "create"),
    openCheckCreate: navigateWithFlag("/checks", "create"),
    openScriptUpload: navigateWithFlag("/scripts", "upload"),
  };
}
