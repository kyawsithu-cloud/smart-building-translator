// Connection to the Python side. In the app window this is pywebview's bridge (no network involved).
// Opened in a normal browser with ?mock, a fake API with sample data is used (UI development only).

let apiPromise = null;

export function getApi() {
  if (apiPromise) return apiPromise;
  apiPromise = new Promise((resolve) => {
    if (new URLSearchParams(location.search).has("mock")) {
      import("./mock-api.js").then((m) => resolve(m.mockApi));
    } else if (window.pywebview && window.pywebview.api) {
      resolve(window.pywebview.api);
    } else {
      window.addEventListener("pywebviewready", () => resolve(window.pywebview.api), { once: true });
    }
  });
  return apiPromise;
}

// Call a Python function; errors become a readable message.
export async function call(name, ...args) {
  const api = await getApi();
  try {
    return await api[name](...args);
  } catch (e) {
    const msg = (e && (e.message || e.toString())) || "Something went wrong";
    throw new Error(msg.replace(/^Error:\s*/, ""));
  }
}
