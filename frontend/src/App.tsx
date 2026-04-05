import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import AIEmailAssistantHero from "./components/AIEmailAssistantHero";
import AppPage from "./AppPage";
import CalendarPage from "./CalendarPage";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/"          element={<AIEmailAssistantHero />} />
        <Route path="/app"       element={<AppPage />} />
        <Route path="/calendar"  element={<CalendarPage />} />
      </Routes>
    </Router>
  );
}

export default App;