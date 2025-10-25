
import React, { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route } from "react-router-dom";
import { auth } from './firebase';
import { onAuthStateChanged, signInAnonymously } from 'firebase/auth';
import Dashboard from './components/Dashboard';
import EmbedDiscoverCharts from './components/embed/EmbedDiscoverCharts';
import EmbedTrajectoryChart from './components/embed/EmbedTrajectoryChart';
import EmbedTrajectoryTicker from './components/embed/EmbedTrajectoryTicker';
import './App.css';
import { AuthContext } from './contexts/AuthContext';

function App() {
  const [authReady, setAuthReady] = useState(false);

  useEffect(() => {
    let signInRequested = false;
    const unsubscribe = onAuthStateChanged(auth, (user) => {
      if (user) {
        setAuthReady(true);
        return;
      }
      if (signInRequested) {
        return;
      }
      signInRequested = true;
      signInAnonymously(auth)
        .then(() => {
          console.log("Signed in anonymously");
        })
        .catch((error) => {
          const errorCode = error.code;
          const errorMessage = error.message;
          console.error(`Anonymous sign-in error: ${errorCode} ${errorMessage}`);
          signInRequested = false;
        });
    });

    return () => unsubscribe();
  }, []);

  if (!authReady) {
    return (
      <div className="app-loading">
        <p>Connecting to data…</p>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ authReady }}>
      <BrowserRouter>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/embed/discover-charts" element={<EmbedDiscoverCharts />} />
          <Route path="/embed/trajectory" element={<EmbedTrajectoryChart />} />
          <Route path="/embed/trajectory-ticker" element={<EmbedTrajectoryTicker />} />
        </Routes>
      </BrowserRouter>
    </AuthContext.Provider>
  );
}

export default App;
