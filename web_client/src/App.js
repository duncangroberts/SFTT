
import React from 'react';
import { BrowserRouter, Routes, Route } from "react-router-dom";
import Dashboard from './components/Dashboard';
import EmbedDiscoverCharts from './components/embed/EmbedDiscoverCharts';
import EmbedTrajectoryChart from './components/embed/EmbedTrajectoryChart';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/embed/discover-charts" element={<EmbedDiscoverCharts />} />
        <Route path="/embed/trajectory" element={<EmbedTrajectoryChart />} />
      </Routes>
    </BrowserRouter>
  );
}

export default App;
