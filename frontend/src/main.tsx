import React from 'react';
import ReactDOM from 'react-dom/client';
import StaticShowcaseApp from './StaticShowcaseApp';
import './static-showcase.css';

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <StaticShowcaseApp />
  </React.StrictMode>,
);
