import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App';
import './styles/index.css';
import './styles/button-motion.css'
import './styles/button-glyph-motion.css';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
