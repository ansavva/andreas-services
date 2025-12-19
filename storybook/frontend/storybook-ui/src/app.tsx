import { Route, Routes } from "react-router-dom";

import PrivateRoute from "@/privateRoute";

import IndexPage from "@/pages/index";
import AboutPage from "@/pages/about";
import StatusPage from "@/pages/status";
import ProjectPage from "@/pages/project";
import ProjectsPage from "@/pages/projects";
import StoryProjectPage from "@/pages/storyProject";
import NotFoundPage from "@/pages/notFound";

function App() {
  return (
    <Routes>
      <Route element={<IndexPage />} path="/" />
      <Route element={<AboutPage />} path="/about" />
      <Route element={<PrivateRoute />}>
        <Route element={<StatusPage />} path="/status" />
      </Route>
      <Route element={<PrivateRoute />}>
        <Route element={<ProjectPage />} path="/project/:project_id" />
      </Route>
      <Route element={<PrivateRoute />}>
        <Route element={<ProjectsPage />} path="/projects" />
      </Route>
      <Route element={<PrivateRoute />}>
        <Route element={<StoryProjectPage />} path="/story-project/:projectId" />
      </Route>
      {/* 404 catch-all route */}
      <Route element={<NotFoundPage />} path="*" />
    </Routes>
  );
}

export default App;
