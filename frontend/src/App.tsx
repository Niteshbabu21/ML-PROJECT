import { Route, Routes } from "react-router-dom";
import Layout from "./components/Layout";
import Dashboard from "./pages/Dashboard";
import Valuation from "./pages/Valuation";
import Explainability from "./pages/Explainability";
import RiskAssessment from "./pages/RiskAssessment";
import Tokenisation from "./pages/Tokenisation";
import ModelPerformance from "./pages/ModelPerformance";
import BlockchainExplorer from "./pages/BlockchainExplorer";
import HistoryPage from "./pages/History";

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="valuation" element={<Valuation />} />
        <Route path="explainability" element={<Explainability />} />
        <Route path="risk" element={<RiskAssessment />} />
        <Route path="tokenisation" element={<Tokenisation />} />
        <Route path="models" element={<ModelPerformance />} />
        <Route path="blockchain" element={<BlockchainExplorer />} />
        <Route path="history" element={<HistoryPage />} />
      </Route>
    </Routes>
  );
}
