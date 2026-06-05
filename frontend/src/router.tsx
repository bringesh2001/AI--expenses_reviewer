import { createBrowserRouter } from "react-router-dom";
import { Layout } from "./components/Layout";
import { AuthGuard } from "./components/AuthGuard";
import LoginPage from "./pages/LoginPage";
import DashboardPage from "./pages/DashboardPage";
import NewSubmissionPage from "./pages/NewSubmissionPage";
import SubmissionDetailPage from "./pages/SubmissionDetailPage";
import PolicyQAPage from "./pages/PolicyQAPage";

function Protected({ children }: { children: React.ReactNode }) {
  return (
    <AuthGuard>
      <Layout>{children}</Layout>
    </AuthGuard>
  );
}

export const router = createBrowserRouter([
  { path: "/login", element: <LoginPage /> },
  {
    path: "/",
    element: <Protected><DashboardPage /></Protected>,
  },
  {
    path: "/submit/new",
    element: <Protected><NewSubmissionPage /></Protected>,
  },
  {
    path: "/submissions/:id",
    element: <Protected><SubmissionDetailPage /></Protected>,
  },
  {
    path: "/policy-qa",
    element: <Protected><PolicyQAPage /></Protected>,
  },
]);
