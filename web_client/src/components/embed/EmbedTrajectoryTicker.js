import React, { useEffect } from 'react';
import TrajectoryTickerTab from '../TrajectoryTickerTab';

function EmbedTrajectoryTicker() {
  useEffect(() => {
    const root = document.documentElement;
    root.classList.add('embed-mode');
    document.body.classList.add('embed-mode');
    document.body.style.overflow = 'hidden';
    return () => {
      root.classList.remove('embed-mode');
      document.body.classList.remove('embed-mode');
      document.body.style.overflow = 'auto';
    };
  }, []);

  return (
    <div className="embed-container ticker-embed">
      <TrajectoryTickerTab />
    </div>
  );
}

export default EmbedTrajectoryTicker;
