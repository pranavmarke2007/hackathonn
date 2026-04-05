import { BrowserRouter as Router, Routes, Route } from "react-router-dom";
import AIEmailAssistantHero from "./components/AIEmailAssistantHero";
import AppPage from "./AppPage";

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<AIEmailAssistantHero />} />
        <Route path="/app" element={<AppPage />} />
      </Routes>
    </Router>
  );
}

export default App;
