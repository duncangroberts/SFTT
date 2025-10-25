
import React, { useState } from 'react';
import DiscoverTab from './DiscoverTab';
import TechTrendsTab from './TechTrendsTab';
import DiscoverChartsTab from './DiscoverChartsTab';
import TrajectoryAnimationsTab from './TrajectoryAnimationsTab';
import TrajectoryTickerTab from './TrajectoryTickerTab';

function Dashboard() {
  const [activeTab, setActiveTab] = useState('discover');

  const renderTabContent = () => {
    switch (activeTab) {
      case 'tech_trends':
        return <TechTrendsTab />;
      case 'discover_charts':
        return <DiscoverChartsTab />;
      case 'trajectory_animations':
        return <TrajectoryAnimationsTab />;
      case 'trajectory_ticker':
        return <TrajectoryTickerTab />;
      case 'discover':
      default:
        return <DiscoverTab />;
    }
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1>Technology Intelligence Dashboard</h1>
      </header>
      <nav className="tab-nav">
        <button 
          className={activeTab === 'discover' ? 'active' : ''} 
          onClick={() => setActiveTab('discover')}
        >
          Discover
        </button>
        <button 
          className={activeTab === 'trajectory_animations' ? 'active' : ''} 
          onClick={() => setActiveTab('trajectory_animations')}
        >
          Trajectory Animations
        </button>
        <button 
          className={activeTab === 'trajectory_ticker' ? 'active' : ''} 
          onClick={() => setActiveTab('trajectory_ticker')}
        >
          Trajectory Ticker
        </button>
        <button 
          className={activeTab === 'discover_charts' ? 'active' : ''} 
          onClick={() => setActiveTab('discover_charts')}
        >
          Discover Charts
        </button>
        <button 
          className={activeTab === 'tech_trends' ? 'active' : ''} 
          onClick={() => setActiveTab('tech_trends')}
        >
          Technology Trends
        </button>
      </nav>
      <main>
        {renderTabContent()}
      </main>
    </div>
  );
}

export default Dashboard;
