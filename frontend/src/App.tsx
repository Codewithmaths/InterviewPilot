import { BrowserRouter, Route, Routes } from "react-router-dom";

import HomePage from "@/pages/Home";
import InterviewerPage from "@/pages/Interviewer";
import CandidatePage from "@/pages/Candidate";
import ReportPage from "@/pages/Report";

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/interviewer/:id" element={<InterviewerPage />} />
        <Route path="/candidate/:id/:roomCode" element={<CandidatePage />} />
        <Route path="/report/:id" element={<ReportPage />} />
      </Routes>
    </BrowserRouter>
  );
}
