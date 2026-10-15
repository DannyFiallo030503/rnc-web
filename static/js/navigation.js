/* El menú funciona con <details>; este comportamiento facilita cerrarlo. */
const mobileMenu = document.querySelector(".mobile-menu");

const sidebarToggle = document.querySelector(".sidebar-toggle");
const workspace = document.querySelector(".workspace-shell");

if (sidebarToggle && workspace) {
  const applySidebarState = (collapsed) => {
    workspace.classList.toggle("sidebar-collapsed", collapsed);
    sidebarToggle.setAttribute("aria-expanded", String(!collapsed));
    const label = collapsed ? "Ampliar barra lateral" : "Plegar barra lateral";
    sidebarToggle.setAttribute("aria-label", label);
    sidebarToggle.title = label;
  };
  try {
    applySidebarState(localStorage.getItem("rnc.sidebar.collapsed") === "true");
  } catch {
    applySidebarState(false);
  }
  sidebarToggle.hidden = false;
  sidebarToggle.addEventListener("click", () => {
    const collapsed = !workspace.classList.contains("sidebar-collapsed");
    applySidebarState(collapsed);
    try {
      localStorage.setItem("rnc.sidebar.collapsed", String(collapsed));
    } catch {
      // El menú sigue funcionando cuando el navegador bloquea almacenamiento.
    }
  });
}

if (mobileMenu) {
  mobileMenu.addEventListener("click", (event) => {
    if (event.target.closest("a")) mobileMenu.open = false;
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && mobileMenu.open) {
      mobileMenu.open = false;
      mobileMenu.querySelector("summary").focus();
    }
  });
  document.addEventListener("click", (event) => {
    if (mobileMenu.open && !mobileMenu.contains(event.target)) {
      mobileMenu.open = false;
    }
  });
}
