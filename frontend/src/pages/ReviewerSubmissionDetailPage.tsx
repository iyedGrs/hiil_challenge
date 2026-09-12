import { useParams } from "react-router-dom";
import { PlaceholderPage } from "./PlaceholderPage";

export function ReviewerSubmissionDetailPage() {
  const { submissionId } = useParams<{ submissionId: string }>();
  return <PlaceholderPage title={`Dossier soumis ${submissionId ?? ""}`} />;
}
