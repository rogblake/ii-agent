"""HTML templates for MCP SSE server widgets."""

from string import Template

# Main widget HTML template - displays E2B sandbox in an iframe
# Use $app_url placeholder for the app URL (using string.Template)
MAIN_WIDGET_HTML_TEMPLATE = Template("""
<!DOCTYPE html>
<html>
  <head>
    <style>
      * {
        margin: 0;
        padding: 0;
        box-sizing: border-box;
      }
      html,
      body {
        width: 100%;
        height: 100%;
        overflow: hidden;
      }
      .widget-container {
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
          sans-serif;
        width: 100%;
        height: 100%;
        display: flex;
        flex-direction: column;
        background: #181e1c;
        position: relative;
      }
      .widget-header {
        display: flex;
        align-items: center;
        padding: 16px 16px 0;
        gap: 12px;
      }
      .widget-header img {
        width: 40px;
        height: 40px;
      }
      .widget-header span {
        color: white;
        font-size: 20px;
        font-weight: 600;
      }
      .header-left {
        display: flex;
        align-items: center;
        gap: 10px;
      }
      .widget-icon {
        font-size: 20px;
      }
      .widget-title {
        font-size: 16px;
        font-weight: 600;
      }
      .widget-status {
        font-size: 12px;
        padding: 4px 10px;
        background: rgba(255, 255, 255, 0.2);
        border-radius: 12px;
      }
      .sandbox-frame {
        flex: 1;
        width: 100%;
        border: none;
        background: #0d1117;
      }
      .loading-state {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #8b949e;
        gap: 16px;
      }
      .loading-state img {
        width: 180px;
        height: 180px;
      }
      .loading-spinner {
        width: 40px;
        height: 40px;
        border: 3px solid #30363d;
        border-top-color: #a6ffff;
        border-radius: 50%;
        animation: spin 1s linear infinite;
      }
      @keyframes spin {
        to {
          transform: rotate(360deg);
        }
      }
      .loading-text {
        font-size: 28px;
        font-weight: 600;
        background: linear-gradient(
          90deg,
          #a6ffff 25%,
          #181e1c 50%,
          #a6ffff 75%
        );
        background-size: 300% 100%;
        -webkit-background-clip: text;
        background-clip: text;
        color: transparent;
        animation: shimmer 1.5s linear infinite;
      }
      .button-container {
        position: absolute;
        bottom: 16px;
        right: 16px;
        display: none;
        gap: 12px;
        align-items: flex-end;
        flex-direction: column;
      }
      .btn-open,
      .btn-fullscreen {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: 8px;
        border-radius: 24px;
        background: #bee6f0;
        border: none;
        outline: none;
        color: #181e1c;
        font-size: 12px;
        font-weight: 600;
        cursor: pointer;
        transition: all 0.2s ease;
        box-shadow: 0 4px 24px rgba(0, 0, 0, 0.16);
      }
      .btn-open:hover,
      .btn-fullscreen:hover {
        background: #a8d5e2;
      }
      .btn-open svg,
      .btn-fullscreen svg {
        width: 16px;
        height: 16px;
      }
      @keyframes shimmer {
        0% {
          background-position: 100% 50%;
        }
        100% {
          background-position: 0% 50%;
        }
      }
      .error-state {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: #f85149;
        gap: 12px;
        padding: 20px;
        text-align: center;
      }
      .error-icon {
        font-size: 32px;
      }
      .sandbox-url {
        font-size: 11px;
        color: rgba(255, 255, 255, 0.6);
        max-width: 200px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      /* Debug Panel Styles */
      .debug-panel {
        position: fixed;
        top: 10px;
        right: 10px;
        background: rgba(0, 0, 0, 0.9);
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 12px;
        max-width: 400px;
        max-height: 80vh;
        overflow-y: auto;
        z-index: 9999;
        font-family: monospace;
        font-size: 11px;
        color: #c9d1d9;
      }
      .debug-toggle {
        position: fixed;
        top: 10px;
        right: 10px;
        background: #238636;
        color: white;
        border: none;
        border-radius: 6px;
        padding: 8px 12px;
        cursor: pointer;
        font-size: 12px;
        font-weight: 600;
        z-index: 10000;
      }
      .debug-toggle:hover {
        background: #2ea043;
      }
      .debug-section {
        margin-bottom: 12px;
        padding-bottom: 12px;
        border-bottom: 1px solid #30363d;
      }
      .debug-section:last-child {
        border-bottom: none;
      }
      .debug-title {
        color: #58a6ff;
        font-weight: bold;
        margin-bottom: 6px;
      }
      .debug-content {
        background: #0d1117;
        padding: 8px;
        border-radius: 4px;
        overflow-x: auto;
        white-space: pre-wrap;
        word-break: break-all;
      }
      .debug-close {
        float: right;
        background: #da3633;
        color: white;
        border: none;
        border-radius: 4px;
        padding: 4px 8px;
        cursor: pointer;
        font-size: 10px;
        margin-bottom: 8px;
      }
      /* Main Content Layout */
      .main-content {
        display: flex;
        flex: 1;
        overflow: hidden;
      }
      .content-area {
        flex: 1;
        display: flex;
        flex-direction: column;
        overflow: hidden;
      }
      /* Events Sidebar Styles */
      .events-sidebar {
        position: absolute;
        top: 16px;
        right: 16px;
        bottom: 0;
        width: 320px;
        background: #181e1c;
        display: flex;
        flex-direction: column;
        transition: transform 0.3s ease;
        z-index: 100;
        height: calc(100vh - 32px);
        border-radius: 12px;
        overflow: hidden;
      }
      .events-sidebar.closed {
        transform: translateX(100%);
        right: 0;
      }
      .sidebar-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        padding: 8px 16px;
        background: #181e1c;
        flex-shrink: 0;
      }
      .sidebar-title {
        color: #ffffff;
        font-size: 16px;
        font-weight: 600;
        display: flex;
        align-items: center;
        gap: 8px;
      }
      .sidebar-title svg {
        width: 16px;
        height: 16px;
      }
      .sidebar-close-btn {
        background: transparent;
        border: none;
        color: #ffffff;
        cursor: pointer;
        padding: 4px;
        border-radius: 4px;
        display: flex;
        align-items: center;
        justify-content: center;
      }
      .events-list {
        flex: 1;
        overflow-y: auto;
        padding: 12px;
        scroll-behavior: smooth;
      }
      .event-item {
        background: #000000;
        border-radius: 8px;
        padding: 12px;
        margin-bottom: 8px;
        animation: slideIn 0.3s ease-out;
      }
      .event-item:last-child {
        margin-bottom: 0;
      }
      @keyframes slideIn {
        from {
          opacity: 0;
          transform: translateX(20px);
        }
        to {
          opacity: 1;
          transform: translateX(0);
        }
      }
      .event-header {
        display: flex;
        align-items: center;
        justify-content: space-between;
        margin-bottom: 8px;
      }
      .event-type {
        font-size: 11px;
        font-weight: 600;
        text-transform: uppercase;
        padding: 2px 8px;
        border-radius: 4px;
        background: #238636;
        color: #ffffff;
      }
      .event-type.error {
        background: #da3633;
      }
      .event-type.warning {
        background: #d29922;
      }
      .event-type.info {
        background: #1f6feb;
      }
      .event-type.tool {
        background: #8957e5;
      }
      .event-type.thought {
        background: #bee6f0;
        color: black;
      }
      .event-time {
        font-size: 10px;
        color: #8b949e;
      }
      .event-content {
        font-size: 14px;
        color: #ffffff;
        line-height: 1.5;
        word-break: break-word;
        white-space: pre-wrap;
      }
      .event-item.thought-item {
        background: rgba(190, 230, 240, 0.18);
        border: 1px solid white;
      }
      .event-item.thought-item .event-content {
        color: #ffffff;
        font-size: 12px;
      }
      .event-item.tool-item {
        border-radius: 12px;
        padding: 8px 12px;
      }
      .event-item.tool-item .event-content {
        font-family: monospace;
        font-size: 12px;
      }
      .event-item.tool-item .event-header {
        display: none;
      }
      .event-item.message-item {
        padding: 0;
        background: none;
      }
      .event-item.message-item .event-header {
        display: none;
      }
      .events-empty {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        height: 100%;
        color: #8b949e;
        font-size: 13px;
        gap: 8px;
      }
      .events-empty svg {
        width: 32px;
        height: 32px;
        opacity: 0.5;
      }
      /* Toggle Sidebar Button */
      .sidebar-toggle-btn {
        position: absolute;
        top: 16px;
        right: 16px;
        background: #bee6f0;
        border: none;
        border-radius: 24px;
        cursor: pointer;
        display: flex;
        align-items: center;
        justify-content: center;
        padding: 8px;
      }
      
      .sidebar-toggle-btn svg {
        width: 16px;
        height: 16px;
      }
      
      /* Sidebar Overlay */
      .sidebar-overlay {
        position: absolute;
        top: 0;
        left: 0;
        right: 0;
        bottom: 0;
        background: rgba(0, 0, 0, 0.5);
        z-index: 99;
        opacity: 0;
        visibility: hidden;
        transition: opacity 0.3s ease, visibility 0.3s ease;
      }
      .sidebar-overlay.visible {
        opacity: 1;
        visibility: visible;
      }
    </style>
  </head>
  <body>
    <!-- Debug Toggle Button -->
    <button class="debug-toggle" style="display: none" onclick="toggleDebug()">
      🐛 Debug
    </button>

    <!-- Debug Panel (hidden by default) -->
    <div class="debug-panel" id="debug-panel" style="display: none">
      <button class="debug-close" onclick="toggleDebug()">Close</button>
      <div style="clear: both"></div>

      <div class="debug-section">
        <div class="debug-title">window.openai.toolInput</div>
        <div class="debug-content" id="debug-toolInput">Loading...</div>
      </div>

      <div class="debug-section">
        <div class="debug-title">window.openai.toolOutput</div>
        <div class="debug-content" id="debug-toolOutput">Loading...</div>
      </div>

      <div class="debug-section">
        <div class="debug-title">window.openai.toolResponseMetadata</div>
        <div class="debug-content" id="debug-toolResponseMetadata">
          Loading...
        </div>
      </div>

      <div class="debug-section">
        <div class="debug-title">window.openai.widgetState</div>
        <div class="debug-content" id="debug-widgetState">Loading...</div>
      </div>

      <div class="debug-section">
        <div class="debug-title">window.openai.displayMode</div>
        <div class="debug-content" id="debug-displayMode">Loading...</div>
      </div>
    </div>

    <div class="widget-container">
      <div class="widget-header">
        <img src="https://agent.ii.inc/images/logo-only.png" alt="logo" />
        <span>II-Agent</span>
      </div>
      <div class="main-content">
        <div class="content-area" id="content-area">
          <div class="loading-state" id="loading">
            <p class="loading-text">Meet II-Agent</p>
            <img
              id="agent-head"
              src="https://agent.ii.inc/images/agent-head.png"
              alt="agent"
            />
            <div
              id="lottie"
              style="width: 180px; height: 180px; display: none"
            ></div>
          </div>
          <div class="button-container" id="button-container">
            <button class="btn-fullscreen" onclick="onRequestFullscreen()">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M15 22.75H9C3.57 22.75 1.25 20.43 1.25 15V9C1.25 3.57 3.57 1.25 9 1.25H15C20.43 1.25 22.75 3.57 22.75 9V15C22.75 20.43 20.43 22.75 15 22.75ZM9 2.75C4.39 2.75 2.75 4.39 2.75 9V15C2.75 19.61 4.39 21.25 9 21.25H15C19.61 21.25 21.25 19.61 21.25 15V9C21.25 4.39 19.61 2.75 15 2.75H9Z"
                  fill="#000000"
                />
                <path
                  d="M5.99945 18.7499C5.80945 18.7499 5.61945 18.6799 5.46945 18.5299C5.17945 18.2399 5.17945 17.7599 5.46945 17.4699L17.4695 5.46994C17.7595 5.17994 18.2395 5.17994 18.5295 5.46994C18.8195 5.75994 18.8195 6.23994 18.5295 6.52994L6.52945 18.5299C6.37945 18.6799 6.18945 18.7499 5.99945 18.7499Z"
                  fill="#000000"
                />
                <path
                  d="M18 10.75C17.59 10.75 17.25 10.41 17.25 10V6.75H14C13.59 6.75 13.25 6.41 13.25 6C13.25 5.59 13.59 5.25 14 5.25H18C18.41 5.25 18.75 5.59 18.75 6V10C18.75 10.41 18.41 10.75 18 10.75Z"
                  fill="#000000"
                />
                <path
                  d="M10 18.75H6C5.59 18.75 5.25 18.41 5.25 18V14C5.25 13.59 5.59 13.25 6 13.25C6.41 13.25 6.75 13.59 6.75 14V17.25H10C10.41 17.25 10.75 17.59 10.75 18C10.75 18.41 10.41 18.75 10 18.75Z"
                  fill="#000000"
                />
                <path
                  d="M17.9995 18.7499C17.8095 18.7499 17.6195 18.6799 17.4695 18.5299L5.46945 6.52994C5.17945 6.23994 5.17945 5.75994 5.46945 5.46994C5.75945 5.17994 6.23945 5.17994 6.52945 5.46994L18.5295 17.4699C18.8195 17.7599 18.8195 18.2399 18.5295 18.5299C18.3795 18.6799 18.1895 18.7499 17.9995 18.7499Z"
                  fill="#000000"
                />
                <path
                  d="M6 10.75C5.59 10.75 5.25 10.41 5.25 10V6C5.25 5.59 5.59 5.25 6 5.25H10C10.41 5.25 10.75 5.59 10.75 6C10.75 6.41 10.41 6.75 10 6.75H6.75V10C6.75 10.41 6.41 10.75 6 10.75Z"
                  fill="#000000"
                />
                <path
                  d="M18 18.75H14C13.59 18.75 13.25 18.41 13.25 18C13.25 17.59 13.59 17.25 14 17.25H17.25V14C17.25 13.59 17.59 13.25 18 13.25C18.41 13.25 18.75 13.59 18.75 14V18C18.75 18.41 18.41 18.75 18 18.75Z"
                  fill="#000000"
                />
              </svg>
            </button>
            <button class="btn-open" onclick="onOpenProject()">
              <svg
                width="24"
                height="24"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M15 22.75H14C13.59 22.75 13.25 22.41 13.25 22C13.25 21.59 13.59 21.25 14 21.25H15C19.61 21.25 21.25 19.61 21.25 15V9C21.25 4.39 19.61 2.75 15 2.75H9C4.39 2.75 2.75 4.39 2.75 9V9.98C2.75 10.39 2.41 10.73 2 10.73C1.59 10.73 1.25 10.39 1.25 9.98V9C1.25 3.57 3.57 1.25 9 1.25H15C20.43 1.25 22.75 3.57 22.75 9V15C22.75 20.43 20.43 22.75 15 22.75Z"
                  fill="#292D32"
                />
                <path
                  d="M12.9995 11.7502C12.8095 11.7502 12.6195 11.6802 12.4695 11.5302C12.1795 11.2402 12.1795 10.7602 12.4695 10.4702L16.2095 6.72021H13.9995C13.5895 6.72021 13.2495 6.38021 13.2495 5.97021C13.2495 5.56021 13.5795 5.22021 13.9995 5.22021H18.0095C18.3095 5.22021 18.5895 5.40021 18.6995 5.68021C18.8195 5.96021 18.7495 6.28022 18.5395 6.50022L13.5295 11.5302C13.3795 11.6802 13.1895 11.7502 12.9995 11.7502Z"
                  fill="#292D32"
                />
                <path
                  d="M18.0098 10.7402C17.5998 10.7402 17.2598 10.4002 17.2598 9.99021V5.97021C17.2598 5.56021 17.5998 5.22021 18.0098 5.22021C18.4198 5.22021 18.7598 5.56021 18.7598 5.97021V9.98021C18.7598 10.4002 18.4198 10.7402 18.0098 10.7402Z"
                  fill="#292D32"
                />
                <path
                  d="M7.85 22.75H5.15C2.49 22.75 1.25 21.51 1.25 18.85V16.15C1.25 13.49 2.49 12.25 5.15 12.25H7.85C10.51 12.25 11.75 13.49 11.75 16.15V18.85C11.75 21.51 10.51 22.75 7.85 22.75ZM5.15 13.75C3.31 13.75 2.75 14.31 2.75 16.15V18.85C2.75 20.69 3.31 21.25 5.15 21.25H7.85C9.69 21.25 10.25 20.69 10.25 18.85V16.15C10.25 14.31 9.69 13.75 7.85 13.75H5.15Z"
                  fill="#292D32"
                />
              </svg>
            </button>
          </div>
          <iframe
            class="sandbox-frame"
            id="sandbox-iframe"
            style="display: none"
          ></iframe>
          <div class="error-state" id="error" style="display: none">
            <span class="error-icon">⚠️</span>
            <span id="error-message">Failed to load sandbox</span>
          </div>
        </div>

        <!-- Sidebar Overlay -->
        <div class="sidebar-overlay" id="sidebar-overlay" onclick="toggleSidebar()"></div>

        <!-- Sidebar Toggle Button -->
        <button
          class="sidebar-toggle-btn sidebar-closed"
          id="sidebar-toggle"
          onclick="toggleSidebar()"
          style="display: none"
        >
          <svg width="28" height="28" viewBox="0 0 28 28" fill="none" xmlns="http://www.w3.org/2000/svg">
            <path d="M1.55469 16.3333C1.55469 14.6454 2.53197 13.1877 3.9503 12.4915C3.90932 12.2222 3.88802 11.9467 3.88802 11.6666C3.88802 8.65973 6.32558 6.22217 9.33247 6.22217C9.58048 6.22217 9.82495 6.23851 10.0647 6.27078C10.8349 4.19939 12.8255 2.72217 15.1658 2.72217C17.9148 2.72217 20.1859 4.75987 20.5556 7.40706C20.702 7.39524 20.8499 7.38883 20.9991 7.38883C24.006 7.38883 26.4436 9.82639 26.4436 12.8333C26.4436 15.8401 24.006 18.2777 20.9991 18.2777C20.7834 18.2777 20.5707 18.2627 20.3611 18.2382C19.8287 19.625 18.4901 20.6111 16.9158 20.6111H16.3325C14.1847 20.6111 12.4436 22.3522 12.4436 24.4999C12.4436 24.9295 12.0954 25.2777 11.6658 25.2777C11.2362 25.2777 10.888 24.9295 10.888 24.4999C10.888 21.4931 13.3256 19.0555 16.3325 19.0555H16.9158C17.9897 19.0555 18.8801 18.2628 19.0319 17.2311C19.0469 17.1289 19.0547 17.024 19.0547 16.9166C19.0547 15.8827 18.3201 15.0183 17.3442 14.8203C16.9236 14.7347 16.6516 14.3249 16.7365 13.9042C16.8113 13.5357 17.1356 13.2802 17.4976 13.2799L17.6541 13.2966L17.9655 13.3741C19.4278 13.8069 20.5079 15.1192 20.5996 16.6994C20.7309 16.7128 20.864 16.7222 20.9991 16.7222C23.1469 16.7222 24.888 14.981 24.888 12.8333C24.888 10.6855 23.1469 8.94439 20.9991 8.94439C20.8468 8.94439 20.6968 8.95329 20.5495 8.97021C20.4473 9.6601 20.2167 10.3084 19.8811 10.8888C19.6661 11.2606 19.191 11.3878 18.8192 11.1729C18.4475 10.9579 18.3203 10.4829 18.5352 10.1111C18.8464 9.57284 19.0326 8.95238 19.0532 8.28966C19.0544 8.24826 19.0547 8.20725 19.0547 8.16661C19.0547 6.01884 17.3135 4.27772 15.1658 4.27772C13.5377 4.27772 12.1416 5.27859 11.5625 6.69916C12.528 7.13315 13.3433 7.83912 13.911 8.71956L14.0477 8.94439L14.1131 9.08719C14.2278 9.43031 14.0891 9.818 13.7637 10.0062C13.4387 10.194 13.0347 10.121 12.7945 9.85129L12.7018 9.72217L12.4983 9.40771C11.9909 8.69812 11.2513 8.16625 10.3928 7.92356C10.0567 7.82855 9.70114 7.77772 9.33247 7.77772C7.18469 7.77772 5.44358 9.51884 5.44358 11.6666C5.44358 12.0457 5.49828 12.4113 5.59852 12.7558C5.66441 12.9821 5.74974 13.2002 5.85373 13.4075L5.96311 13.6111L6.02843 13.7539C6.14319 14.097 6.0044 14.4847 5.67904 14.6729C5.35378 14.8609 4.94852 14.7883 4.70833 14.518L4.61719 14.3888L4.46224 14.1032C4.44642 14.0717 4.43189 14.0395 4.41667 14.0075C3.63295 14.4858 3.11024 15.3491 3.11024 16.3333C3.11024 17.8368 4.32902 19.0555 5.83247 19.0555C7.01653 19.0555 8.02567 18.2985 8.39974 17.2402C8.54305 16.8355 8.98837 16.6231 9.39323 16.7662C9.79789 16.9096 10.0103 17.3549 9.86719 17.7597C9.28022 19.42 7.69612 20.6111 5.83247 20.6111C3.46993 20.6111 1.55469 18.6959 1.55469 16.3333Z" fill="#212121"/>
            <path d="M10.3627 10.9072C10.7819 11.0011 11.0461 11.4177 10.9521 11.8369C10.8592 12.2516 11.0834 12.8555 11.7086 13.2071C12.3335 13.558 12.9644 13.4349 13.2703 13.1402C13.5796 12.8422 14.072 12.8522 14.3701 13.1615C14.6682 13.4708 14.6597 13.9633 14.3504 14.2613L14.1787 14.4117C13.2913 15.1204 11.9915 15.1498 10.9461 14.5621C9.83084 13.9351 9.16576 12.6958 9.43455 11.4966C9.52853 11.0777 9.94377 10.8135 10.3627 10.9072Z" fill="#212121"/>
          </svg>
        </button>

        <!-- Events Sidebar -->
        <div class="events-sidebar closed" id="events-sidebar">
          <div class="sidebar-header">
            <div class="sidebar-title">
              II-Agent Thought
            </div>
            <button class="sidebar-close-btn" onclick="toggleSidebar()">
              <svg
                width="20"
                height="20"
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M18 6L6 18M6 6l12 12"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
            </button>
          </div>
          <div class="events-list" id="events-list">
            <div class="events-empty" id="events-empty">
              <svg
                viewBox="0 0 24 24"
                fill="none"
                xmlns="http://www.w3.org/2000/svg"
              >
                <path
                  d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2"
                  stroke="currentColor"
                  stroke-width="2"
                  stroke-linecap="round"
                  stroke-linejoin="round"
                />
              </svg>
              <span>No events yet</span>
            </div>
          </div>
        </div>
      </div>
    </div>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/bodymovin/5.12.2/lottie.min.js"></script>
    <script src="https://cdn.socket.io/4.7.5/socket.io.min.js"></script>
    <script>
      // Debug Panel Functions
      function toggleDebug() {
        const panel = document.getElementById("debug-panel");
        const button = document.querySelector(".debug-toggle");
        if (panel.style.display === "none") {
          panel.style.display = "block";
          button.style.display = "none";
          updateDebugPanel();
        } else {
          panel.style.display = "none";
          button.style.display = "block";
        }
      }

      function updateDebugPanel() {
        // Update toolInput
        const toolInput = window.openai?.toolInput || null;
        document.getElementById("debug-toolInput").textContent = JSON.stringify(
          toolInput,
          null,
          2
        );

        // Update toolOutput
        const toolOutput = window.openai?.toolOutput || null;
        document.getElementById("debug-toolOutput").textContent =
          JSON.stringify(toolOutput, null, 2);

        // Update toolResponseMetadata
        const toolResponseMetadata =
          window.openai?.toolResponseMetadata || null;
        document.getElementById("debug-toolResponseMetadata").textContent =
          JSON.stringify(toolResponseMetadata, null, 2);

        // Update widgetState
        const widgetState = window.openai?.widgetState || null;
        document.getElementById("debug-widgetState").textContent =
          JSON.stringify(widgetState, null, 2);

        // Update displayMode
        const displayMode = window.openai?.displayMode || null;
        document.getElementById("debug-displayMode").textContent =
          JSON.stringify(displayMode, null, 2);
      }

      // Auto-refresh debug panel every 2 seconds if visible
      setInterval(() => {
        const panel = document.getElementById("debug-panel");
        if (panel && panel.style.display !== "none") {
          updateDebugPanel();
        }
      }, 2000);

      // Sidebar Functions
      let sidebarOpen = false;
      let userClosedSidebar = window.openai?.widgetState?.userClosedSidebar || false;
      let renderedEventIds = new Set();

      function showSidebarToggle() {
        const toggleBtn = document.getElementById("sidebar-toggle");
        toggleBtn.style.display = "flex";
      }

      function openSidebar() {
        if (sidebarOpen || userClosedSidebar) return;
        const sidebar = document.getElementById("events-sidebar");
        const toggleBtn = document.getElementById("sidebar-toggle");
        const overlay = document.getElementById("sidebar-overlay");
        sidebarOpen = true;
        sidebar.classList.remove("closed");
        toggleBtn.classList.remove("sidebar-closed");
        overlay.classList.add("visible");
      }

      function toggleSidebar() {
        const sidebar = document.getElementById("events-sidebar");
        const toggleBtn = document.getElementById("sidebar-toggle");
        const overlay = document.getElementById("sidebar-overlay");

        sidebarOpen = !sidebarOpen;

        if (sidebarOpen) {
          sidebar.classList.remove("closed");
          toggleBtn.classList.remove("sidebar-closed");
          overlay.classList.add("visible");
          userClosedSidebar = false;
        } else {
          sidebar.classList.add("closed");
          toggleBtn.classList.add("sidebar-closed");
          overlay.classList.remove("visible");
          userClosedSidebar = true;
        }

        // Save userClosedSidebar to widgetState
        const currentState = window.openai?.widgetState || {};
        window.openai.setWidgetState({ ...currentState, userClosedSidebar });
      }
      window.toggleSidebar = toggleSidebar;

      function getEventTypeClass(type) {
        const typeLower = (type || "").toLowerCase();
        if (typeLower.includes("error")) return "error";
        if (typeLower.includes("warning")) return "warning";
        if (typeLower.includes("thinking")) return "thought";
        if (typeLower.includes("tool")) return "tool";
        if (typeLower.includes("info") || typeLower.includes("status"))
          return "info";
        return "";
      }

      function formatEventTime(timestamp) {
        if (!timestamp) return "";
        try {
          const date = new Date(timestamp);
          return date.toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
        } catch (e) {
          return "";
        }
      }

      function getEventDisplayInfo(event) {
        const type = (event.type || "").toLowerCase();
        const content = event.content;

        // Skip metrics_update and tool_result events
        if (
          type === "metrics_update" ||
          type === "tool_result" ||
          type === "status_update" ||
          type === "connection_established" ||
          type === "system" ||
          type === "sandbox_status"
        ) {
          return null;
        }

        // Handle agent_thinking - show as "Thought"
        if (type === "agent_thinking") {
          if (!content.text) return null;
          return {
            tag: "Thought",
            tagClass: "thought",
            itemClass: "thought-item",
            content: content.text,
          };
        }

        if (type === "tool_call" && content.tool_name === "message_user") {
          return {
            tag: "Message User",
            tagClass: "info",
            itemClass: "message-item",
            content: content?.tool_input?.message,
          };
        }

        // Handle tool_call - show name only
        if (type === "tool_call" || type.includes("tool")) {
          let toolName = "";
          if (typeof content === "object" && content) {
            toolName =
              content.tool_display_name || content.tool_name || "";
          } else if (typeof content === "string") {
            toolName = content;
          }
          return {
            tag: "Tool",
            tagClass: "tool",
            itemClass: "tool-item",
            content: toolName || "Unknown tool",
          };
        }

        // Default handling
        let displayContent = "";
        if (typeof content === "string") {
          displayContent = content;
        } else if (content) {
          displayContent =
            content.message || content.text || JSON.stringify(content);
        }

        return {
          tag: event.type || "Event",
          tagClass: getEventTypeClass(event.type),
          itemClass: event.type === 'user_message' ? "message-item" : "",
          content: displayContent,
        };
      }

      function renderEvents(events) {
        const eventsList = document.getElementById("events-list");
        const eventsEmpty = document.getElementById("events-empty");

        if (!events || events.length === 0) {
          eventsEmpty.style.display = "flex";
          return;
        }

        // Filter and process events
        const processedEvents = events
          .map((e) => ({ ...e, displayInfo: getEventDisplayInfo(e) }))
          .filter((e) => e.displayInfo !== null);

        if (processedEvents.length === 0) {
          eventsEmpty.style.display = "flex";
          return;
        }

        eventsEmpty.style.display = "none";

        // Auto-open sidebar when events exist
        openSidebar();

        // Sort by created_at ascending (oldest first, newest at bottom)
        const sortedEvents = [...processedEvents].sort((a, b) => {
          const dateA = new Date(a.created_at || 0);
          const dateB = new Date(b.created_at || 0);
          return dateA - dateB;
        });

        // Find new events that haven't been rendered yet
        const newEvents = sortedEvents.filter((e) => {
          const eventId = e.id || e.created_at || JSON.stringify(e);
          return !renderedEventIds.has(eventId);
        });

        // Only render new events (append, don't re-render all)
        newEvents.forEach((event) => {
          const eventId = event.id || event.created_at || JSON.stringify(event);
          renderedEventIds.add(eventId);

          const info = event.displayInfo;
          const eventEl = document.createElement("div");
          eventEl.className =
            "event-item" + (info.itemClass ? " " + info.itemClass : "");
          eventEl.innerHTML =
            '<div class="event-header">' +
            '<span class="event-type ' +
            info.tagClass +
            '">' +
            info.tag +
            "</span>" +
            '<span class="event-time">' +
            formatEventTime(event.created_at) +
            "</span>" +
            "</div>" +
            '<div class="event-content">' +
            escapeHtml(info.content) +
            "</div>";
          eventsList.appendChild(eventEl);
        });

        // Auto-scroll to bottom if there are new events
        if (newEvents.length > 0) {
          eventsList.scrollTop = eventsList.scrollHeight;
        }
      }

      function escapeHtml(text) {
        if (!text) return "";
        const div = document.createElement("div");
        div.textContent = text;
        return div.innerHTML;
      }

      // Auto-refresh events from widget state
      setInterval(() => {
        const events = window.openai?.widgetState?.events;
        if (events) {
          renderEvents(events);
        }
      }, 2000);

      // Widget that gets session_id from widget state and polls for sandbox status
      (function () {
        const iframe = document.getElementById("sandbox-iframe");
        const loading = document.getElementById("loading");
        const error = document.getElementById("error");
        const errorMessage = document.getElementById("error-message");
        const loadingText = loading.querySelector(".loading-text");
        const header = document.querySelector(".widget-header");
        const agentHead = document.getElementById("agent-head");
        const lottieContainer = document.getElementById("lottie");
        const buttonContainer = document.getElementById("button-container");
        const btnFullscreen = document.querySelector(".btn-fullscreen");

        const anim = lottie.loadAnimation({
          container: document.getElementById("lottie"),
          renderer: "svg",
          loop: true,
          autoplay: false,
          path: "https://lottie.host/d13c3b0f-2fc0-42eb-8338-40a7493e94b6/vBfnLSEaGJ.json",
        });

        // Configuration (injected from server)
        const APP_URL = "$app_url";
        const API_URL = "$api_url";

        let sessionId = null;
        let pollCount = 0;
        const MAX_POLL_COUNT = 80;
        const POLL_INTERVAL_MS = 10000;

        // Socket.IO connection
        let socket = null;
        let socketConnected = false;

        function connectSocketIO(token, session_uuid) {
          if (socket && socketConnected) {
            console.log("Socket.IO already connected");
            return;
          }

          if (!token || !session_uuid) {
            console.log(
              "Socket.IO: Missing token or session_uuid, skipping connection"
            );
            return;
          }

          socket = io(API_URL, {
            auth: { token, session_uuid },
            transports: ["websocket", "polling"],
            timeout: 15000,
            reconnection: false,
          });

          socket.on("connect", () => {
            socketConnected = true;

            // Join the session room
            socket.emit("join_session", { session_uuid });
          });

          socket.on("chat_event", (data) => {
            // Update widget state with new events if needed
            if (data && data.type) {
              const currentState = window.openai?.widgetState || {};
              const events = currentState.events || [];
              events.push({
                id: data.id || Date.now().toString(),
                type: data.type,
                content: data.content,
                created_at: new Date().toISOString(),
              });
              window.openai.setWidgetState({ ...currentState, events });
            }
          });

          socket.on("connect_error", (error) => {
            console.error("Socket.IO connection error:", error);
            socketConnected = false;
          });

          socket.on("disconnect", (reason) => {
            console.log("Socket.IO disconnected:", reason);
            socketConnected = false;
            socket = null;
          });
        }

        function showIframe(url) {
          iframe.src = url;
          iframe.style.display = "block";
          loading.style.display = "none";
          error.style.display = "none";
          header.style.display = "none";
        }

        function showError(msg) {
          error.style.display = "flex";
          loading.style.display = "none";
          iframe.style.display = "none";
          errorMessage.textContent = msg;
        }

        function showLoading(msg) {
          loading.style.display = "flex";
          loadingText.textContent = msg || "Loading...";
          iframe.style.display = "none";
          error.style.display = "none";
          header.style.display = "flex";
        }

        function onOpenProject() {
          window.openai.openExternal({ href: APP_URL + "/" + sessionId });
        }

        function onRequestFullscreen() {
          window?.openai?.requestDisplayMode?.({ mode: "fullscreen" });
        }

        function updateButtonVisibility() {
          // Hide fullscreen button if already in fullscreen mode
          const displayMode = window.openai?.displayMode;
          if (btnFullscreen) {
            if (displayMode === "fullscreen") {
              btnFullscreen.style.display = "none";
            } else {
              btnFullscreen.style.display = "flex";
            }
          }
        }

        // Expose to global scope for onclick handler
        window.onOpenProject = onOpenProject;
        window.onRequestFullscreen = onRequestFullscreen;

        // Check display mode periodically to update button visibility
        setInterval(updateButtonVisibility, 500);

        async function fetchSessionStatus() {
          if (!sessionId || sessionId === "" || sessionId.startsWith("$$")) {
            return null;
          }
          try {
            // Use window.openai.callTool to call refresh_session_status
            const result = await window.openai.callTool(
              "refresh_session_status",
              {
                session_id: sessionId,
              }
            );

            // Extract public_url from the tool result
            // The result structure is: { structuredContent: { session_id, status, sandbox_id, public_url, events, token } }
            const data = result?.structuredContent;
            if (data) {
              const currentState = window.openai?.widgetState || {};
              window.openai.setWidgetState({
                ...currentState,
                events: data.events,
                public_url: data.public_url,
                user_id: data.user_id,
                token: data.token,
              });

              // Connect to Socket.IO with token and session_id
              if (data.token && sessionId) {
                connectSocketIO(data.token, sessionId);
              }

              return data.public_url;
            }
          } catch (err) {
            console.debug("Failed to fetch session status:", err);
          }
          return null;
        }

        async function pollForPublicUrl() {
          // Keep polling until we get public_url or timeout
          while (pollCount < MAX_POLL_COUNT) {
            pollCount++;
            showLoading("Preview will be available soon");
            agentHead.style.display = "none";
            lottieContainer.style.display = "block";
            buttonContainer.style.display = "flex";
            anim.play();

            const public_url_from_state =
              window.openai.widgetState && window.openai.widgetState.public_url;
            if (public_url_from_state) {
              showIframe(public_url_from_state);
              return; // Success - stop polling
            }

            try {
              const publicUrl = await fetchSessionStatus();
              if (publicUrl) {
                showIframe(publicUrl);
                return; // Success - stop polling
              }
            } catch (err) {
              console.debug("Poll error:", err);
            }

            // Wait 10 seconds before next poll
            await new Promise((resolve) =>
              setTimeout(resolve, POLL_INTERVAL_MS)
            );
          }

          // Timeout after max polls
          showError("Website creation timed out. Please try again.");
        }

        async function startWithSessionId(sid) {
          sessionId = sid;
          showLoading("Preview will be available soon");
          buttonContainer.style.display = "flex";
          showSidebarToggle();

          // Try to connect Socket.IO with token from widgetState or toolOutput
          const token =
            window.openai?.widgetState?.token ||
            window.openai?.toolOutput?.token;
          if (token && sid) {
            connectSocketIO(token, sid);
          }

          if (isSlideAgent()) {
            if (sessionId) {
              showIframe(getPresentationUrl());
              return;
            }
          }

          // Start polling loop only for website_build tasks
          if (isWebsiteBuildAgent()) {
            pollForPublicUrl();
          }
        }

        function getSessionIdFromWidgetState() {
          // Get session_id from OpenAI tool output
          if (window.openai?.toolOutput?.session_id) {
            return window.openai.toolOutput.session_id;
          }
          return null;
        }

        function getAgentTypeFromWidgetState() {
          return (
            window.openai?.toolInput?.agent_type ||
            window.openai?.toolOutput?.agent_type ||
            window.openai?.widgetState?.agent_type ||
            "website_build"
          );
        }

        function isSlideAgent() {
          const agentType = getAgentTypeFromWidgetState();
          return agentType === "slide" || agentType === "slide_nano_banana";
        }

        function isWebsiteBuildAgent() {
          return getAgentTypeFromWidgetState() === "website_build";
        }

        function getPresentationUrl() {
          return APP_URL + "/presentations/" + sessionId;
        }

        function initialize() {
          const sid = getSessionIdFromWidgetState();

          if (!sid) {
            // No session_id available - show starting message
            buttonContainer.style.display = "none";
            // Keep checking for session_id periodically
            setTimeout(initialize, 1000);
            // Show "Starting Project..." when toolInput.prompt is available
            if (window.openai?.toolInput?.prompt) {
              showLoading("Starting Project...");
            }
          } else {
            // Session ID available - start fetching status
            startWithSessionId(sid);
          }
        }

        // Initialize
        initialize();

        iframe.onerror = function () {
          showError("Failed to load sandbox iframe");
        };
      })();
    </script>
  </body>
</html>

""")
