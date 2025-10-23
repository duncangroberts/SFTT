
import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { auth } from './firebase';
import { signInAnonymously } from 'firebase/auth';
import Dashboard from './components/Dashboard';
import EmbedDiscoverCharts from './components/embed/EmbedDiscoverCharts';
import EmbedTrajectoryChart from './components/embed/EmbedTrajectoryChart';
import './App.css';

function App() {
  useEffect(() => {
    signInAnonymously(auth)
      .then(() => {
        // Signed in..
        console.log("Signed in anonymously");
      })
      .catch((error) => {
        const errorCode = error.code;
        const errorMessage = error.message;
        console.error(`Anonymous sign-in error: ${errorCode} ${errorMessage}`);
      });
  }, []);

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
