import { Navigate, Route, Routes } from "react-router-dom";
import { AppShell } from "../components/AppShell";
import { CaseDetailPage } from "../pages/CaseDetailPage";
import { CasesListPage } from "../pages/CasesListPage";
import { LoginPage } from "../pages/LoginPage";
import { NewCasePage } from "../pages/NewCasePage";
import { NotFoundPage } from "../pages/NotFoundPage";
import { ReviewerSubmissionDetailPage } from "../pages/ReviewerSubmissionDetailPage";
import { ReviewerSubmissionsPage } from "../pages/ReviewerSubmissionsPage";
import { RequireAuth, RequireRole, roleHome } from "../session/guards";
import { useSession } from "../session/SessionContext";

function IndexRedirect() {
  const { status, user } = useSession();
  if (status === "loading") return null;
  if (status === "anonymous" || !user) return <Navigate to="/login" replace />;
  return <Navigate to={roleHome(user.role)} replace />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RequireAuth>
            <AppShell />
          </RequireAuth>
        }
      >
        <Route index element={<IndexRedirect />} />

        <Route
          path="cases"
          element={
            <RequireRole role="preparer">
              <CasesListPage />
            </RequireRole>
          }
        />
        <Route
          path="cases/new"
          element={
            <RequireRole role="preparer">
              <NewCasePage />
            </RequireRole>
          }
        />
        <Route
          path="cases/:caseId"
          element={
            <RequireRole role="preparer">
              <CaseDetailPage />
            </RequireRole>
          }
        />

        <Route
          path="reviewer/submissions"
          element={
            <RequireRole role="reviewer">
              <ReviewerSubmissionsPage />
            </RequireRole>
          }
        />
        <Route
          path="reviewer/submissions/:submissionId"
          element={
            <RequireRole role="reviewer">
              <ReviewerSubmissionDetailPage />
            </RequireRole>
          }
        />

        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  );
}
