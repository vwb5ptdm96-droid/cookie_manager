import { useRouter } from "vue-router";

function navigateWithFlag(path: string, flag: string) {
  const router = useRouter();

  return () => router.push({ path, query: { [flag]: "1" } });
}

export function useGlobalQuickActions() {
  const router = useRouter();
  return {
    openEnvironmentChecks: navigateWithFlag("/environment", "autorun"),
    openScriptUpload: navigateWithFlag("/scripts", "upload"),
    openDutyDesk: () => router.push("/auto-repair-tickets"),
  };
}
