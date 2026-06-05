import { createBrowserRouter } from "react-router-dom";
import { Layout } from "./components/Layout";
import DashboardPage from "./pages/DashboardPage";
import NewSubmissionPage from "./pages/NewSubmissionPage";
import SubmissionDetailPage from "./pages/SubmissionDetailPage";
import PolicyQAPage from "./pages/PolicyQAPage";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <Layout><DashboardPage /></Layout>,
  },
  {
    path: "/submit/new",
    element: <Layout><NewSubmissionPage /></Layout>,
  },
  {
    path: "/submissions/:id",
    element: <Layout><SubmissionDetailPage /></Layout>,
  },
  {
    path: "/policy-qa",
    element: <Layout><PolicyQAPage /></Layout>,
  },
]);
