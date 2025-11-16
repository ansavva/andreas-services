import { Route, Routes } from "react-router-dom";

import PrivateRoute from "@/privateRoute";

import IndexPage from "@/pages/index";
import AboutPage from "@/pages/about";
import StatusPage from "@/pages/status";
import ProjectPage from "@/pages/project";
import ProjectsPage from "@/pages/projects";

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
    </Routes>
  );
}

export default App;
