import { BrowserRouter } from "react-router-dom";
import { ToastProvider } from "./components/Toast";
import { AppRoutes } from "./routes/AppRoutes";
import { SessionProvider } from "./session/SessionContext";

export function App() {
  return (
    <BrowserRouter>
      <SessionProvider>
        <ToastProvider>
          <AppRoutes />
        </ToastProvider>
      </SessionProvider>
    </BrowserRouter>
  );
}
