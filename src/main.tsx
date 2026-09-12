import React from "react";
import ReactDOM from "react-dom/client";
import { App } from "./App";
import { BubbleOverlay } from "./BubbleOverlay";
import "./styles.css";

const root = ReactDOM.createRoot(document.getElementById("root") as HTMLElement);
const isBubbleRoute = window.location.hash === "#/bubble";

root.render(
  <React.StrictMode>
    {isBubbleRoute ? <BubbleOverlay /> : <App />}
  </React.StrictMode>,
);
