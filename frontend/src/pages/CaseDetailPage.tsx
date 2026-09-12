import { useParams } from "react-router-dom";
import { PlaceholderPage } from "./PlaceholderPage";

export function CaseDetailPage() {
  const { caseId } = useParams<{ caseId: string }>();
  return <PlaceholderPage title={`Dossier ${caseId ?? ""}`} />;
}
