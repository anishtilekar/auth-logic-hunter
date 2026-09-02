import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route } from "react-router";
import Dashboard from "@/pages/Dashboard";
import NewRun from "@/pages/NewRun";
import RunDetail from "@/pages/RunDetail";

const queryClient = new QueryClient();

export default function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/runs/new" element={<NewRun />} />
          <Route path="/runs/:id" element={<RunDetail />} />
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  );
}
