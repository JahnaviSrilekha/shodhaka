import { AppHeader, useHealth } from "./components/AppHeader";
import { AnalysisPage } from "./features/analysis/AnalysisPage";
import { DocumentPage } from "./features/editor/DocumentPage";
import { OrgPage } from "./features/orgs/OrgPage";
import { OrgsPage } from "./features/orgs/OrgsPage";
import { PackEditorPage } from "./features/packs/PackEditorPage";
import { ProjectPage } from "./features/projects/ProjectPage";
import { useHashRoute } from "./hooks/useHashRoute";
import { ToastProvider } from "./hooks/useToast";

// Pages get a plain { org, project } scope, never the route object: spreading a route into a
// link would carry its `page` along and point the link at the wrong screen.
export function App() {
  const route = useHashRoute();
  const health = useHealth();
  const key = JSON.stringify(route);
  return (
    <ToastProvider>
      <AppHeader health={health} route={route} />
      {route.page === "home" && <OrgsPage />}
      {route.page === "org" && <OrgPage key={key} org={route.org} />}
      {route.page === "project" && <ProjectPage key={key} scope={{ org: route.org, project: route.project }} health={health} />}
      {route.page === "pack" && <PackEditorPage key={`${route.org}/${route.project}/${route.pack}`} scope={{ org: route.org, project: route.project }} packId={route.pack} />}
      {route.page === "analysis" && <AnalysisPage key={`${route.project}/${route.id}`} scope={{ org: route.org, project: route.project }} id={route.id} findingId={route.finding} />}
      {route.page === "document" && <DocumentPage key={`${route.project}/${route.id}/${route.path}`} scope={{ org: route.org, project: route.project }} id={route.id} path={route.path} findingId={route.finding} />}
    </ToastProvider>
  );
}
