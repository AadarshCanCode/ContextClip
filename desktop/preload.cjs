const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("contextClip", {
  getConfig: () => ipcRenderer.invoke("contextclip:get-config"),
  showBubble: (payload) => ipcRenderer.send("contextclip:bubble-show", payload),
  hideBubble: () => ipcRenderer.send("contextclip:bubble-hide"),
});
