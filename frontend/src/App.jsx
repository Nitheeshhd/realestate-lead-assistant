import { Navigate, Route, Routes } from "react-router-dom";
import { session } from "./api.js";
import Shell from "./components/Shell.jsx";
import Chat from "./pages/Chat.jsx";
import Login from "./pages/Login.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Leads from "./pages/Leads.jsx";
import LeadDetail from "./pages/LeadDetail.jsx";
import Handoffs from "./pages/Handoffs.jsx";
import Facts from "./pages/Facts.jsx";
import Slots from "./pages/Slots.jsx";

function Guard({ head, children }) {
  const s = session.get();
  if (!s) return <Navigate to="/login" replace />;
  if (head && s.role !== "sales_head") return <Navigate to="/leads" replace />;
  return children;
}

export default function App() {
  const s = session.get();
  return (
    <Routes>
      <Route path="/" element={<Chat />} />
      <Route path="/login" element={<Login />} />
      <Route element={<Guard><Shell /></Guard>}>
        <Route path="/dashboard" element={<Guard head><Dashboard /></Guard>} />
        <Route path="/leads" element={<Leads />} />
        <Route path="/leads/:id" element={<LeadDetail />} />
        <Route path="/handoffs" element={<Handoffs />} />
        <Route path="/facts" element={<Guard head><Facts /></Guard>} />
        <Route path="/slots" element={<Guard head><Slots /></Guard>} />
      </Route>
      <Route path="*" element={<Navigate to={s ? "/leads" : "/"} replace />} />
    </Routes>
  );
}
