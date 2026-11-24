import React from 'react';
import ReactDOM from 'react-dom/client';
import { createBrowserRouter, RouterProvider } from 'react-router-dom';
// Rediseño v2: Plus Jakarta Sans (títulos y métricas), Rubik (texto) y Spline Sans Mono (RFC, UUID, cifras).
import '@fontsource/plus-jakarta-sans/600.css';
import '@fontsource/plus-jakarta-sans/700.css';
import '@fontsource/rubik/400.css';
import '@fontsource/rubik/500.css';
import '@fontsource/rubik/600.css';
import '@fontsource/rubik/700.css';
import '@fontsource/spline-sans-mono/400.css';
import '@fontsource/spline-sans-mono/500.css';
import '@fontsource/material-symbols-outlined';
import './theme-tokens.css';
import './styles.css';
import './stitch-refinements.css';
import App from './App';
const router = createBrowserRouter([{ path: '*', element: <App /> }]);
ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RouterProvider router={router} />
  </React.StrictMode>,
);
